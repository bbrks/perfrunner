from optparse import OptionParser

from mc_bin_client.mc_bin_client import MemcachedClient, memcacheConstants

from perfrunner.helpers.misc import server_group
from perfrunner.helpers.monitor import Monitor
from perfrunner.helpers.remote import RemoteHelper
from perfrunner.helpers.rest import RestHelper
from perfrunner.settings import ClusterSpec, TestConfig
from perfrunner.tests import TargetIterator


class ClusterManager(object):

    def __init__(self, cluster_spec, test_config):
        self.cluster_spec = cluster_spec
        self.test_config = test_config

        self.rest = RestHelper(cluster_spec)
        self.remote = RemoteHelper(cluster_spec)
        self.monitor = Monitor(cluster_spec)

        self.clusters = cluster_spec.get_clusters().values()
        self.initial_nodes = test_config.get_initial_nodes()
        self.mem_quota = test_config.get_mem_quota()
        self.group_number = test_config.get_group_number() or 1

    def set_data_path(self):
        data_path, index_path = self.cluster_spec.get_paths()
        for cluster in self.clusters:
            for host_port in cluster:
                self.rest.set_data_path(host_port, data_path, index_path)

    def set_auth(self):
        for cluster in self.clusters:
            for host_port in cluster:
                self.rest.set_auth(host_port)

    def set_mem_quota(self):
        for cluster in self.clusters:
            for host_port in cluster:
                self.rest.set_mem_quota(host_port, self.mem_quota)

    def create_server_groups(self):
        for cluster in self.clusters:
            master = cluster[0]
            for i in range(1, self.group_number):
                name = 'Group {}'.format(i + 1)
                self.rest.create_server_group(master, name=name)

    def add_nodes(self):
        for cluster in self.clusters:
            master = cluster[0]
            if self.group_number > 1:
                groups = self.rest.get_server_groups(master)
            else:
                groups = {}
            for i, host_port in enumerate(cluster[1:self.initial_nodes],
                                          start=1):
                host = host_port.split(':')[0]
                uri = groups.get(server_group(cluster[:self.initial_nodes],
                                              self.group_number, i))
                self.rest.add_node(master, host, uri)

    def rebalance(self):
        for cluster in self.clusters:
            master = cluster[0]
            known_nodes = cluster[:self.initial_nodes]
            ejected_nodes = []
            self.rest.rebalance(master, known_nodes, ejected_nodes)
            self.monitor.monitor_rebalance(master)

    def create_buckets(self):
        threads_number = self.test_config.get_mrw_threads_number()
        replica_number = self.test_config.get_replica_number()
        if replica_number is None:
            replica_number = 1

        num_buckets = self.test_config.get_num_buckets()
        ram_quota = self.mem_quota / num_buckets
        buckets = ['bucket-{}'.format(i + 1) for i in xrange(num_buckets)]

        for cluster in self.clusters:
            master = cluster[0]
            for name in buckets:
                self.rest.create_bucket(master, name, ram_quota,
                                        replica_number=replica_number,
                                        threads_number=threads_number)

    def configure_auto_compaction(self):
        compaction_settings = self.test_config.get_compaction_settings()
        for cluster in self.clusters:
            master = cluster[0]
            self.rest.configure_auto_compaction(master, compaction_settings)

    def configure_internal_settings(self):
        internal_settings = self.test_config.get_internal_settings()
        for cluster in self.clusters:
            master = cluster[0]
            for parameter, value in internal_settings.items():
                self.rest.set_internal_settings(master,
                                                {parameter: int(value)})

    def clean_memory(self):
        self.remote.reset_swap()
        self.remote.drop_caches()
        self.remote.set_swappiness()

    def restart_with_alternative_swt(self):
        swt = self.test_config.get_swt()
        if swt is not None:
            self.remote.restart_with_alternative_swt(swt=swt)

    def enable_auto_failover(self):
        for cluster in self.clusters:
            master = cluster[0]
            self.rest.enable_auto_failover(master)

    def wait_until_warmed_up(self):
        target_iterator = TargetIterator(self.cluster_spec, self.test_config)
        for target in target_iterator:
            self.monitor.monitor_warmup(target)

    def change_watermarks(self):
        watermark_settings = self.test_config.get_watermark_settings()
        _, password = self.cluster_spec.get_rest_credentials()

        for bucket in self.test_config.get_buckets():
            for host in self.cluster_spec.get_all_hosts():
                mc = MemcachedClient(host=host, port=11210)
                mc.sasl_auth_plain(user=bucket, password=password)
                for key, val in watermark_settings.items():
                    val = int(val) / 100.0  # string -> ratio
                    mem_quota = self.mem_quota * 1024 ** 2  # Mb -> bytes
                    val = str(int(val * mem_quota))
                    mc.set_param(key, val, memcacheConstants.ENGINE_PARAM_FLUSH)


def get_options():
    usage = '%prog -c cluster -t test_config'

    parser = OptionParser(usage)

    parser.add_option('-c', dest='cluster_spec_fname',
                      help='path to cluster specification file',
                      metavar='cluster.spec')
    parser.add_option('-t', dest='test_config_fname',
                      help='path to test configuration file',
                      metavar='my_test.test')

    options, _ = parser.parse_args()
    if not options.cluster_spec_fname or not options.test_config_fname:
        parser.error('Missing mandatory parameter')

    return options


def main():
    options = get_options()

    cluster_spec = ClusterSpec()
    cluster_spec.parse(options.cluster_spec_fname)
    test_config = TestConfig()
    test_config.parse(options.test_config_fname)

    cm = ClusterManager(cluster_spec, test_config)
    cm.restart_with_alternative_swt()
    cm.configure_internal_settings()
    cm.set_data_path()
    cm.set_auth()
    cm.set_mem_quota()
    if cm.group_number > 1:
        cm.create_server_groups()
    if cm.initial_nodes > 1:
        cm.add_nodes()
        cm.rebalance()
    cm.create_buckets()
    cm.wait_until_warmed_up()
    cm.configure_auto_compaction()
    cm.enable_auto_failover()
    cm.change_watermarks()
    cm.clean_memory()

if __name__ == '__main__':
    main()
