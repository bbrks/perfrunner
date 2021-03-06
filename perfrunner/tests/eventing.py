import json

from perfrunner.helpers.cbmonitor import timeit, with_stats
from perfrunner.tests import PerfTest, TargetIterator


class EventingTest(PerfTest):

    """Eventing test base class.

    This is base class for eventing related operations required
    to measure eventing performance parameters.
    """

    FUNCTION_SAMPLE_FILE = "tests/eventing/config/function_sample.json"
    FUNCTION_ENABLE_SAMPLE_FILE = "tests/eventing/config/enable_function_sample.json"
    COLLECTORS = {'eventing_stats': True}

    def __init__(self, *args):
        super().__init__(*args)

        self.functions = self.test_config.eventing_settings.functions
        self.worker_count = self.test_config.eventing_settings.worker_count
        self.cpp_worker_thread_count = self.test_config.eventing_settings.cpp_worker_thread_count

        self.function_nodes = self.cluster_spec.servers_by_role('eventing')

        for master in self.cluster_spec.masters:
            self.rest.add_rbac_user(
                host=master,
                bucket="eventing",
                password="password",
                roles=['admin'],
            )

        self.target_iterator = TargetIterator(self.cluster_spec, self.test_config, "eventing")

    def set_functions(self):
        with open(self.FUNCTION_SAMPLE_FILE) as f:
            func = json.load(f)

        func["settings"]["worker_count"] = self.worker_count
        func["settings"]["cpp_worker_thread_count"] = self.cpp_worker_thread_count
        for name, filename in self.functions.items():
            with open(filename, 'r') as myfile:
                code = myfile.read()
                func["appname"] = name
                func["appcode"] = code
            function = json.dumps(func)
            self.rest.create_function(node=self.function_nodes[0], payload=function, name=name)
            self.rest.deploy_function(node=self.function_nodes[0], payload=function, name=name)
            self.monitor.wait_for_bootstrap(node=self.function_nodes[0], function=name)

    def enable_function(self):
        with open(self.FUNCTION_ENABLE_SAMPLE_FILE) as f:
            func = json.load(f)

        func["worker_count"] = self.worker_count
        for name, filename in self.functions.items():
            function = json.dumps(func)
            self.rest.enable_function(node=self.function_nodes[0], payload=function, name=name)
            self.monitor.wait_for_bootstrap(node=self.function_nodes[0], function=name)

    @timeit
    @with_stats
    def load_and_wait(self):
        self.load()
        self.access_bg()
        self.sleep()

    def run(self):
        self.set_functions()

        time_elapsed = self.load_and_wait()

        self.report_kpi(time_elapsed)


class FunctionsThroughputTest(EventingTest):
    def _report_kpi(self, time_elapsed):
        self.reporter.post(
            *self.metrics.function_throughput(time_elapsed)
        )
