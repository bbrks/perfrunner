import os.path
from urllib.parse import urlparse

from fabric.api import get, put, run, settings
from fabric.exceptions import CommandTimeout, NetworkError

from logger import logger
from perfrunner.helpers.misc import uhex
from perfrunner.remote import Remote
from perfrunner.remote.context import (
    all_servers,
    master_server,
    servers_by_role,
)


class RemoteLinux(Remote):

    CB_DIR = '/opt/couchbase'

    PROCESSES = ('beam.smp', 'memcached', 'epmd', 'cbq-engine', 'indexer',
                 'cbft', 'goport', 'goxdcr', 'couch_view_index_updater',
                 'moxi', 'spring')

    @property
    def package(self):
        if self.os.upper() in ('UBUNTU', 'DEBIAN'):
            return 'deb'
        else:
            return 'rpm'

    @master_server
    def detect_centos_release(self) -> str:
        """Detect CentOS release (e.g., 6 or 7).

        Possible values:
        - CentOS release 6.x (Final)
        - CentOS Linux release 7.2.1511 (Core)
        """
        return run('cat /etc/redhat-release').split()[-2][0]

    @master_server
    def detect_ubuntu_release(self):
        return run('lsb_release -sr').strip()

    def run_cbindex_command(self, options):
        cmd = "/opt/couchbase/bin/cbindex {options}".format(options=options)

        logger.info('Running: {}'.format(cmd))
        run(cmd, shell_escape=False, pty=False)

    def build_index(self, index_node, bucket_indexes):
        all_indexes = ",".join(bucket_indexes)
        options = \
            "-auth=Administrator:password " \
            "-server {index_node}:8091 " \
            "-type build " \
            "-indexes {all_indexes}".format(index_node=index_node,
                                            all_indexes=all_indexes)

        self.run_cbindex_command(options)

    def create_index(self, index_nodes, bucket, indexes, storage):
        # Remember what bucket:index was created
        bucket_indexes = []

        for index, field in indexes.items():
            options = \
                "-auth=Administrator:password " \
                "-server {index_node}:8091 " \
                "-type create " \
                "-bucket {bucket} " \
                "-fields={field}".format(index_node=index_nodes[0],
                                         bucket=bucket,
                                         field=field)

            if storage == 'memdb' or storage == 'plasma':
                options = '{options} -using {db}'.format(options=options,
                                                         db=storage)

            with_str = r'{\\\"defer_build\\\":true}'
            options = "{options} -index {index} -with=\\\"{with_str}\\\"" \
                .format(options=options, index=index, with_str=with_str)

            bucket_indexes.append("{}:{}".format(bucket, index))
            self.run_cbindex_command(options)

        return bucket_indexes

    @master_server
    def build_secondary_index(self, index_nodes, bucket, indexes, storage):
        logger.info('building secondary indexes')

        # Create index but do not build
        bucket_indexes = self.create_index(index_nodes, bucket, indexes, storage)

        # build indexes
        self.build_index(index_nodes[0], bucket_indexes)

    @all_servers
    def reset_swap(self):
        logger.info('Resetting swap')
        run('swapoff --all && swapon --all')

    @all_servers
    def drop_caches(self):
        logger.info('Dropping memory cache')
        run('sync && echo 3 > /proc/sys/vm/drop_caches')

    @all_servers
    def set_swappiness(self):
        logger.info('Changing swappiness to 0')
        run('sysctl vm.swappiness=0')

    @all_servers
    def disable_thp(self):
        for path in (
            '/sys/kernel/mm/transparent_hugepage/enabled',
            '/sys/kernel/mm/redhat_transparent_hugepage/enabled',
            '/sys/kernel/mm/transparent_hugepage/defrag',
        ):
            run('echo never > {}'.format(path), quiet=True)

    @all_servers
    def collect_info(self):
        logger.info('Running cbcollect_info')

        run('rm -f /tmp/*.zip')

        fname = '/tmp/{}.zip'.format(uhex())
        try:
            r = run('{}/bin/cbcollect_info {}'.format(self.CB_DIR, fname),
                    warn_only=True, timeout=1200)
        except CommandTimeout:
            logger.error('cbcollect_info timed out')
            return
        if not r.return_code:
            get('{}'.format(fname))
            run('rm -f {}'.format(fname))

    @all_servers
    def clean_data(self):
        for path in self.cluster_spec.paths:
            run('rm -fr {}/*'.format(path))
        run('rm -fr {}'.format(self.CB_DIR))

    @all_servers
    def kill_processes(self):
        logger.info('Killing {}'.format(', '.join(self.PROCESSES)))
        run('killall -9 {}'.format(' '.join(self.PROCESSES)),
            warn_only=True, quiet=True)

    def shutdown(self, host):
        with settings(host_string=host):
            logger.info('Killing {}'.format(', '.join(self.PROCESSES)))
            run('killall -9 {}'.format(' '.join(self.PROCESSES)),
                warn_only=True, quiet=True)

    @all_servers
    def uninstall_couchbase(self):
        logger.info('Uninstalling Couchbase Server')
        if self.package == 'deb':
            run('yes | apt-get remove couchbase-server', quiet=True)
            run('yes | apt-get remove couchbase-server-dbg', quiet=True)
            run('yes | apt-get remove couchbase-server-community', quiet=True)
        else:
            run('yes | yum remove couchbase-server', quiet=True)
            run('yes | yum remove couchbase-server-debuginfo', quiet=True)
            run('yes | yum remove couchbase-server-community', quiet=True)

    def upload_iss_files(self, release: str):
        pass

    @all_servers
    def install_couchbase(self, url: str):
        self.wget(url, outdir='/tmp')
        filename = urlparse(url).path.split('/')[-1]

        logger.info('Installing Couchbase Server')
        if self.package == 'deb':
            run('yes | apt-get install gdebi')
            run('yes | gdebi /tmp/{}'.format(filename))
        else:
            run('yes | rpm -i /tmp/{}'.format(filename))

    @all_servers
    def restart(self):
        logger.info('Restarting server')
        run('systemctl restart couchbase-server', pty=False)

    @all_servers
    def restart_with_alternative_num_vbuckets(self, num_vbuckets):
        logger.info('Changing number of vbuckets to {}'.format(num_vbuckets))
        run('systemctl set-environment COUCHBASE_NUM_VBUCKETS={}'
            .format(num_vbuckets))
        run('systemctl restart couchbase-server', pty=False)
        run('systemctl unset-environment COUCHBASE_NUM_VBUCKETS')

    @all_servers
    def stop_server(self):
        logger.info('Stopping Couchbase Server')
        run('systemctl stop couchbase-server', pty=False)

    @all_servers
    def start_server(self):
        logger.info('Starting Couchbase Server')
        run('systemctl start couchbase-server', pty=False)

    def detect_if(self):
        stdout = run("ip route list | grep default")
        return stdout.strip().split()[4]

    def detect_ip(self, _if):
        stdout = run('ifdata -pa {}'.format(_if))
        return stdout.strip()

    @all_servers
    def disable_wan(self):
        logger.info('Disabling WAN effects')
        _if = self.detect_if()
        run('tc qdisc del dev {} root'.format(_if), warn_only=True, quiet=True)

    @all_servers
    def enable_wan(self):
        logger.info('Enabling WAN effects')
        _if = self.detect_if()
        for cmd in (
            'tc qdisc add dev {} handle 1: root htb',
            'tc class add dev {} parent 1: classid 1:1 htb rate 1gbit',
            'tc class add dev {} parent 1:1 classid 1:11 htb rate 1gbit',
            'tc qdisc add dev {} parent 1:11 handle 10: netem delay 40ms 2ms '
            'loss 0.005% 50% duplicate 0.005% corrupt 0.005%',
        ):
            run(cmd.format(_if))

    @all_servers
    def filter_wan(self, src_list, dest_list):
        logger.info('Filtering WAN effects')
        _if = self.detect_if()

        if self.detect_ip(_if) in src_list:
            _filter = dest_list
        else:
            _filter = src_list

        for ip in _filter:
            run('tc filter add dev {} protocol ip prio 1 u32 '
                'match ip dst {} flowid 1:11'.format(_if, ip))

    @all_servers
    def detect_core_dumps(self):
        # Based on kernel.core_pattern = /data/core-%e-%p
        r = run('ls /data/core*', quiet=True)
        if not r.return_code:
            return r.split()
        else:
            return []

    @all_servers
    def tune_log_rotation(self):
        logger.info('Tune log rotation so that it happens less frequently')
        run('sed -i "s/num_files, [0-9]*/num_files, 50/" '
            '/opt/couchbase/etc/couchbase/static_config')

    @master_server
    def restore_fts(self, archive_path, repo_path):
        cmd = \
            "/opt/couchbase/bin/cbbackupmgr restore " \
            "--archive {} --repo {} --threads 30 " \
            "--cluster http://localhost:8091 " \
            "--username Administrator --password password " \
            "--disable-ft-indexes --disable-gsi-indexes".format(
                archive_path,
                repo_path,
            )

        logger.info("Running: {}".format(cmd))
        run(cmd)

    @all_servers
    def fio(self, config):
        logger.info('Running fio job: {}'.format(config))
        filename = os.path.basename(config)
        remote_path = os.path.join('/tmp', filename)
        put(config, remote_path)
        return run('fio --minimal {}'.format(remote_path))

    def detect_auto_failover(self, host):
        with settings(host_string=host):
            r = run('grep "Starting failing over" '
                    '/opt/couchbase/var/lib/couchbase/logs/info.log', quiet=True)
            if not r.return_code:
                return r.strip().split(',')[1]

    def detect_hard_failover_start(self, host):
        with settings(host_string=host):
            r = run('grep "Starting failing" '
                    '/opt/couchbase/var/lib/couchbase/logs/info.log', quiet=True)
            if not r.return_code:
                return r.strip().split(',')[1]

    def detect_graceful_failover_start(self, host):
        with settings(host_string=host):
            r = run('grep "Starting vbucket moves" '
                    '/opt/couchbase/var/lib/couchbase/logs/info.log', quiet=True)
            if not r.return_code:
                return r.strip().split(',')[1]

    def detect_failover_end(self, host):
        with settings(host_string=host):
            r = run('grep "Failed over \'" '
                    '/opt/couchbase/var/lib/couchbase/logs/info.log', quiet=True)
            if not r.return_code:
                return r.strip().split(',')[1]

    @property
    def num_vcpu(self):
        return int(run('lscpu -a -e | wc -l')) - 1

    @property
    def num_cores(self):
        return int(run('lscpu | grep socket').strip().split()[-1])

    @all_servers
    def disable_cpu(self):
        logger.info('Throttling CPU resources')
        reserved_cores = {i for i in range(0, 2 * self.num_cores, 2)}
        all_cores = {i for i in range(self.num_vcpu)}

        for i in all_cores - reserved_cores:
            run('echo 0 > /sys/devices/system/cpu/cpu{}/online'.format(i))

    @all_servers
    def enable_cpu(self):
        logger.info('Enabling all CPU cores')
        for i in range(self.num_vcpu):
            run('echo 1 > /sys/devices/system/cpu/cpu{}/online'.format(i))

    @servers_by_role(roles=['index'])
    def kill_process_on_index_node(self, process):
        logger.info('Killing following process on index node: {}'.format(process))
        run("killall {}".format(process))

    def get_disk_usage(self, host, path, human_readable=True):
        with settings(host_string=host):
            if human_readable:
                return run("du -h {}".format(path))
            data = run("du -sb {}/@2i".format(path))
            return int(data.split()[0])

    def get_indexer_rss(self, host):
        with settings(host_string=host):
            data = run("ps -eo rss,comm | grep indexer")
            return int(data.split()[0])

    @all_servers
    def set_master_password(self, password='password'):
        logger.info('Enabling encrypted secrets')
        run('systemctl set-environment CB_MASTER_PASSWORD={}'.format(password))

    @all_servers
    def unset_master_password(self):
        logger.info('Disabling encrypted secrets')
        run('systemctl unset-environment CB_MASTER_PASSWORD')

    def grub_config(self):
        logger.info('Changing GRUB configuration')
        run('grub2-mkconfig -o /boot/grub2/grub.cfg')

    def reboot(self):
        logger.info('Rebooting the node')
        run('reboot', quiet=True, pty=False)

    @servers_by_role(roles=['fts', 'index'])
    def tune_memory_settings(self, size):
        logger.info('Changing kernel memory to {}'.format(size))
        run("sed -i 's/quiet/quiet mem={}/' /etc/default/grub".format(size))
        self.grub_config()
        self.reboot()

    @servers_by_role(roles=['fts', 'index'])
    def reset_memory_settings(self):
        logger.info('Resetting kernel memory settings')
        run("sed -ir 's/ mem=[0-9]*[kmgKMG]//' /etc/default/grub")
        self.grub_config()
        self.reboot()

    def is_up(self, host_string: str) -> bool:
        with settings(host_string=host_string):
            try:
                result = run(":")
                return result.return_code == 0  # 0 means success
            except NetworkError:
                return False

    @master_server
    def get_manifest(self):
        logger.info('Getting manifest from host node')
        get("{}/manifest.xml".format(self.CB_DIR), local_path="./")
