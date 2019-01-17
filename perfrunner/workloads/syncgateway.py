from perfrunner.settings import PhaseSettings, ClusterSpec
from perfrunner.helpers.local import run_cmd, restart_memcached


BINARY_NAME = "bin/ycsb"
BINARY_PATH = "YCSB"

LOAD_USERS_CMD = " load syncgateway -s -P {workload} -p syncgateway.loadmode=users -threads 50 " \
                 "-p syncgateway.host={hosts} -p memcached.host={memcached_host} -p recordcount={total_users} " \
                 "-p syncgateway.channels={total_channels} -p syncgateway.channelsperuser={channels_per_user} " \
                 "-p insertstart={insertstart} -p exportfile={exportfile} -p syncgateway.starchannel={starchannel}"

LOAD_DOCS_CMD = " load syncgateway -s -P {workload} -p recordcount={total_docs} -p fieldcount={fieldcount}" \
                "-p fieldlength={fieldlength} -threads {threads} " \
                "-p syncgateway.host={hosts} -p syncgateway.auth=false " \
                "-p memcached.host={memcached_host} -p syncgateway.totalusers={total_users} " \
                "-p syncgateway.channels={total_channels} -p syncgateway.channelsperuser={channels_per_user} " \
                "-p insertstart={insertstart} -p exportfile={exportfile}"

INIT_USERS_CMD = " run syncgateway -s -P {workload} -p recordcount={total_docs} -p operationcount=50 " \
                 "-p maxexecutiontime=36000 -threads 50 -p syncgateway.host={hosts} " \
                 "-p syncgateway.auth={auth} -p memcached.host={memcached_host} " \
                 "-p syncgateway.totalusers={total_users} -p syncgateway.runmode=changesonly " \
                 "-p syncgateway.sequencestart={sequence_start} -p syncgateway.initusers=true " \
                 "-p insertstart={insertstart} -p readproportion=1 -p syncgateway.feedmode=normal " \
                 "-p exportfile={exportfile}"

GRANT_ACCESS_CMD = " run syncgateway -s -P {workload} -p recordcount={total_docs} -p operationcount=50 " \
                 "-p maxexecutiontime=36000 -threads 50 -p syncgateway.host={hosts} " \
                 "-p syncgateway.auth={auth} -p memcached.host={memcached_host} " \
                 "-p syncgateway.totalusers={total_users} -p syncgateway.runmode=changesonly " \
                 "-p syncgateway.sequencestart={sequence_start} " \
                 "-p insertstart={insertstart} -p readproportion=1 -p syncgateway.feedmode=normal " \
                 "-p exportfile={exportfile} -p syncgateway.channelspergrant={channels_per_grant} " \
                 "-p syncgateway.grantaccesstoall={grant_access}"

RUN_TEST_CMD = " run syncgateway -s -P {workload} -p recordcount={total_docs} -p operationcount={total_docs} " \
               "-p fieldcount={fieldcount} -p maxexecutiontime={time} -threads {threads} " \
               "-p writeallfields={writeallfields} -p fieldlength={fieldlength} " \
               "-p readallfields={readallfields} -p syncgateway.host={hosts} -p syncgateway.auth={auth} " \
               "-p memcached.host={memcached_host} -p syncgateway.totalusers={total_users} " \
               "-p syncgateway.roundtrip={roundtrip} -p insertstart={insertstart} " \
               "-p syncgateway.readmode={read_mode} -p syncgateway.insertmode={insert_mode} " \
               "-p syncgateway.sequencestart={sequence_start} -p syncgateway.initusers=false " \
               "-p readproportion={readproportion} -p updateproportion={updateproportion} " \
               "-p scanproportion={scanproportion}  -p syncgateway.updatefieldcount={updatefieldcount} " \
               "-p insertproportion={insertproportion} -p exportfile={exportfile} " \
               "-p syncgateway.feedmode={feedmode} -p syncgateway.grantaccessinscan={grant_access_in_scan}"


def get_offset(workload_settings, worker_id):
    max_inserts = int(workload_settings.syncgateway_settings.max_inserts_per_instance);
    local_offset = worker_id * max_inserts
    return int(workload_settings.syncgateway_settings.insertstart) + local_offset


def get_hosts(cluster, workload_settings):
    return ','.join(cluster.servers[:int(workload_settings.syncgateway_settings.nodes)])


def syncgateway_start_memcached(workload_settings: PhaseSettings, timer: int, worker_id: int, cluster: ClusterSpec):
    restart_memcached(mem_limit=20000, port=8000, mem_host=cluster.workers[0])


def syncgateway_load_users(workload_settings: PhaseSettings, timer: int, worker_id: int, cluster: ClusterSpec):
    sgs = workload_settings.syncgateway_settings
    log_file_name = "{}_loadusers_{}.log".format(sgs.log_title, worker_id)
    res_file_name = "{}_loadusers_{}.result".format(sgs.log_title, worker_id)
    if sgs.replication_type == 'PUSH':
        phosts = '172.23.100.194'
    else:
        phosts = get_hosts(cluster, workload_settings)
    params = LOAD_USERS_CMD.format(workload=sgs.workload,
                                   hosts=phosts,
                                   memcached_host=cluster.workers[0],
                                   total_users=sgs.users,
                                   total_channels=sgs.channels,
                                   channels_per_user=sgs.channels_per_user,
                                   insertstart=get_offset(workload_settings, worker_id),
                                   exportfile=res_file_name,
                                   starchannel=sgs.starchannel)

    path = getInstanceHome(workload_settings, worker_id)
    run_cmd(path, BINARY_NAME, params, log_file_name)


def syncgateway_load_docs(workload_settings: PhaseSettings, timer: int, worker_id: int, cluster: ClusterSpec):
    sgs = workload_settings.syncgateway_settings
    log_file_name = "{}_loaddocs_{}.log".format(sgs.log_title, worker_id)
    res_file_name = "{}_loaddocs_{}.result".format(sgs.log_title, worker_id)
    if sgs.replication_type == 'PUSH':
        phosts = '172.23.100.194'
    else:
        phosts = get_hosts(cluster, workload_settings)
    params = LOAD_DOCS_CMD.format(workload=sgs.workload,
                                  hosts=phosts,
                                  threads=sgs.threads_per_instance,
                                  total_docs=sgs.documents,
                                  fieldlength=sgs.fieldlength,
                                  fieldcount=sgs.fieldcount,
                                  memcached_host=cluster.workers[0],
                                  total_users=sgs.users,
                                  total_channels=sgs.channels,
                                  channels_per_user=sgs.channels_per_user,
                                  insertstart=get_offset(workload_settings, worker_id),
                                  exportfile=res_file_name)

    path = getInstanceHome(workload_settings, worker_id)
    run_cmd(path, BINARY_NAME, params, log_file_name)


def syncgateway_init_users(workload_settings: PhaseSettings, timer: int, worker_id: int, cluster: ClusterSpec):
    sgs = workload_settings.syncgateway_settings
    log_file_name = "{}_initusers_{}.log".format(sgs.log_title, worker_id)
    res_file_name = "{}_initusers_{}.result".format(sgs.log_title, worker_id)
    if sgs.replication_type == 'PUSH':
        phosts = '172.23.100.194'
    else:
        phosts = get_hosts(cluster, workload_settings)
    params = INIT_USERS_CMD.format(workload=sgs.workload,
                                  hosts=phosts,
                                  total_docs=sgs.documents,
                                  memcached_host=cluster.workers[0],
                                  auth=sgs.auth,
                                  total_users=sgs.users,
                                  insertstart=get_offset(workload_settings, worker_id),
                                  sequence_start = int(sgs.users) + int(sgs.documents) + 1,
                                  exportfile=res_file_name)

    path = getInstanceHome(workload_settings, worker_id)
    run_cmd(path, BINARY_NAME, params, log_file_name)


def syncgateway_grant_access(workload_settings: PhaseSettings, timer: int, worker_id: int, cluster: ClusterSpec):
    sgs = workload_settings.syncgateway_settings
    log_file_name = "{}_grantaccess_{}.log".format(sgs.log_title, worker_id)
    res_file_name = "{}_grantaccess_{}.result".format(sgs.log_title, worker_id)
    if sgs.replication_type == 'PUSH':
        phosts = '172.23.100.194'
    else:
        phosts = get_hosts(cluster, workload_settings)
    params = GRANT_ACCESS_CMD.format(workload=sgs.workload,
                                     hosts=phosts,
                                     total_docs=sgs.documents,
                                     memcached_host=cluster.workers[0],
                                     auth=sgs.auth,
                                     total_users=sgs.users,
                                     insertstart=get_offset(workload_settings, worker_id),
                                     sequence_start=int(sgs.users) + int(sgs.documents) + 1,
                                     exportfile=res_file_name,
                                     grant_access=sgs.grant_access,
                                     channels_per_grant=sgs.channels_per_grant)

    path = getInstanceHome(workload_settings, worker_id)
    run_cmd(path, BINARY_NAME, params, log_file_name)



def syncgateway_run_test(workload_settings: PhaseSettings, timer: int, worker_id: int, cluster: ClusterSpec):
    sgs = workload_settings.syncgateway_settings
    log_file_name = "{}_runtest_{}.log".format(sgs.log_title, worker_id)
    res_file_name = "{}_runtest_{}.result".format(sgs.log_title, worker_id)
    if sgs.replication_type == 'PUSH':
        phosts = '172.23.100.194'
    else:
        phosts = get_hosts(cluster, workload_settings)
    params = RUN_TEST_CMD.format(workload=sgs.workload,
                                 hosts=phosts,
                                 writeallfields=sgs.writeallfields,
                                 readallfields=sgs.readallfields,
                                 fieldlength=sgs.fieldlength,
                                 fieldcount=sgs.fieldcount,
                                 total_docs=sgs.documents_workset,
                                 memcached_host=cluster.workers[0],
                                 auth=sgs.auth,
                                 total_users=sgs.users,
                                 insertstart=get_offset(workload_settings, worker_id),
                                 sequence_start=int(sgs.users) + int(sgs.documents) + 1,
                                 read_mode=sgs.read_mode,
                                 insert_mode=sgs.insert_mode,
                                 threads=sgs.threads_per_instance,
                                 time=timer,
                                 roundtrip=sgs.roundtrip_write,
                                 readproportion=sgs.readproportion,
                                 updateproportion=sgs.updateproportion,
                                 insertproportion=sgs.insertproportion,
                                 scanproportion=sgs.scanproportion,
                                 updatefieldcount=sgs.updatefieldcount,
                                 exportfile=res_file_name,
                                 feedmode=sgs.feed_mode,
                                 grant_access_in_scan=sgs.grant_access_in_scan)

    path = getInstanceHome(workload_settings, worker_id)
    run_cmd(path, BINARY_NAME, params, log_file_name)


def getInstanceHome(workload_settings, worker_id):
    path = BINARY_PATH
    if worker_id:
        instances = int(workload_settings.syncgateway_settings.clients)
        instance_id =  int((worker_id + instances - 1) / instances)
        path = "{}_{}".format(path, instance_id)
    return path