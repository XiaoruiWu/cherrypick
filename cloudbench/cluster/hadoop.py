from .base import Cluster
from cloudbench.apps.hadoop import HADOOP_USER, HADOOP_DIR
from cloudbench.util import parallel

# The instruction is taken from:
# https://chawlasumit.wordpress.com/2015/03/09/install-a-multi-node-hadoop-cluster-on-ubuntu-14-04/

CoreSiteTemplate="""<?xml version="1.0" encoding="UTF-8"?>
<?xml-stylesheet type="text/xsl" href="configuration.xsl"?>
<configuration>
{0}
</configuration>
"""

MapRedSiteTemplate="""<?xml version="1.0"?>
<?xml-stylesheet type="text/xsl" href="configuration.xsl"?>
<configuration>
{0}
</configuration>
"""

HdfsSiteTemplate="""<?xml version="1.0" encoding="UTF-8"?>
<?xml-stylesheet type="text/xsl" href="configuration.xsl"?>
<configuration>
{0}
</configuration>
"""

YarnSiteTemplate="""<?xml version="1.0"?>
<configuration>
{0}
</configuration>
"""

Ports=[54310, 54311, ]

def modify_hadoop_config(config, f):
    command = "sudo su - {0} -c cat <<EOT > {1}{2}\n{3}\nEOT"
    command = command.format(HADOOP_USER, HADOOP_DIR, f, config)
    return command

class HadoopCluster(Cluster):
    def __init__(self, master_, slaves_):
        self.master = master_
        self.slaves_ = slaves_

        super(HadoopCluster, self).__init__(self.all_nodes(), HADOOP_USER)

    @property
    def master(self):
        return self.master_

    @master.setter
    def master(self, value):
        self.master_ = value

    def master_ip(self):
        return self.master_.intf_ip('eth0')

    @property
    def slaves(self):
        return self.slaves_

    @slaves.setter
    def slaves(self, slaves):
        self.slaves_ = slaves


    def setup_core_site(self):
        config = """
           <property>
             <name>hadoop.tmp.dir</name>
             <value>file:///home/{0}/tmp</value>
             <description>Temporary Directory.</description>
           </property>

           <property>
             <name>fs.defaultFS</name>
             <value>hdfs://{1}:54310</value>
             <description>Use HDFS as file storage engine</description>
           </property> 
        """

        config = CoreSiteTemplate.format(config.format(HADOOP_USER, self.master_ip()))
        command = modify_hadoop_config(config, '/etc/hadoop/core-site.xml')
    
        # Upload the file in parallel
        parallel(lambda node: node.script(command), self.all_nodes())

    def all_nodes(self):
        return list(set([self.master] + self.slaves))

    def setup_mapred_site(self):
        config = """
<property>
 <name>mapreduce.jobtracker.address</name>
 <value>{0}:54311</value>
 <description>The host and port that the MapReduce job tracker runs
  at. If "local", then jobs are run in-process as a single map
  and reduce task.
</description>
</property>
<property>
 <name>mapreduce.framework.name</name>
 <value>yarn</value>
 <description>The framework for running mapreduce jobs</description>
</property>
"""
        config = MapRedSiteTemplate.format(config.format(self.master_ip()))
        self.master.script(modify_hadoop_config(config, '/etc/hadoop/mapred-site.xml'))

    def setup_hdfs_site(self):
        dirs = ["/home/{0}/hdfs/datanode", "/home/{0}/hdfs/namenode"]
        def create_hdfs_dirs(vm):
            for d in dirs:
                vm.script('sudo su - {0} -c "mkdir -p {1}"'.format(HADOOP_USER, d))

        parallel(create_hdfs_dirs, self.all_nodes())

        config = """
<property>
 <name>dfs.replication</name>
 <value>2</value>
 <description>Default block replication.
  The actual number of replications can be specified when the file is created.
  The default is used if replication is not specified in create time.
 </description>
</property>
<property>
 <name>dfs.namenode.name.dir</name>
 <value>/home/{0}/hdfs/namenode</value>
 <description>Determines where on the local filesystem the DFS name node should store the name table(fsimage). If this is a comma-delimited list of directories then the name table is replicated in all of the directories, for redundancy.
 </description>
</property>
<property>
 <name>dfs.datanode.data.dir</name>
 <value>/home/{0}/hdfs/datanode</value>
 <description>Determines where on the local filesystem an DFS data node should store its blocks. If this is a comma-delimited list of directories, then data will be stored in all named directories, typically on different devices. Directories that do not exist are ignored.
 </description>
</property>
"""
        config = HdfsSiteTemplate.format(config.format(HADOOP_USER))
        command = modify_hadoop_config(config, '/etc/hadoop/hdfs-site.xml')
        parallel(lambda vm: vm.script(command), self.all_nodes())

    def setup_yarn_site(self):
        config = """
<property>
 <name>yarn.nodemanager.aux-services</name>
 <value>mapreduce_shuffle</value>
</property>
<property>
 <name>yarn.resourcemanager.scheduler.address</name>
 <value>{0}:8030</value>
</property> 
<property>
 <name>yarn.resourcemanager.address</name>
 <value>{0}:8032</value>
</property>
<property>
  <name>yarn.resourcemanager.webapp.address</name>
  <value>{0}:8088</value>
</property>
<property>
  <name>yarn.resourcemanager.resource-tracker.address</name>
  <value>{0}:8031</value>
</property>
<property>
  <name>yarn.resourcemanager.admin.address</name>
  <value>{0}:8033</value>
</property>
"""
        config = YarnSiteTemplate.format(config.format(self.master_ip())) 
        command = modify_hadoop_config(config, '/etc/hadoop/yarn-site.xml')
        parallel(lambda vm: vm.script(command), self.all_nodes())

    def setup_slaves(self):
        names = set() 
        for node in self.all_nodes():
            names.add(node.intf_ip('eth0'))

        config = "\n".join(list(names))
        command = modify_hadoop_config(config, '/etc/hadoop/slaves')
        self.master.script(command)

    def setup(self):
        self.setup_keys()
        self.setup_core_site()
        self.setup_mapred_site()
        self.setup_hdfs_site()
        self.setup_yarn_site()
        self.setup_slaves()

    def hadoop_user_cmd(self, cmd):
        return 'sudo su - {0} -c {1}'.format(HADOOP_USER, cmd)

    def start_dfs(self):
        self.master.script(
                self.hadoop_user_cmd('"start-dfs.sh"'))

    def stop_dfs(self):
        self.master.script(
                self.hadoop_user_cmd('"stop-dfs.sh"'))

    def restart_dfs(self):
        self.stop_dfs()
        self.start_dfs()

    def start_yarn(self):
        self.master.script(
                self.hadoop_user_cmd('"start-yarn.sh"'))

    def stop_yarn(self):
        self.master.script(
                self.hadoop_user_cmd('"stop-yarn.sh"'))

    def restart_yarn(self):
        self.stop_yarn()
        self.start_yarn()

    def format_hdfs(self):
        remove_hdfs_dir = self.hadoop_user_cmd('"rm -rf /home/{0}/hdfs"'.format(HADOOP_USER))
        parallel(lambda vm: vm.script(remove_hdfs_dir), self.all_nodes())

        remove_hdfs_dir = self.hadoop_user_cmd('"rm -rf /home/{0}/tmp"'.format(HADOOP_USER))
        parallel(lambda vm: vm.script(remove_hdfs_dir), self.all_nodes())

        self.master.script(
                self.hadoop_user_cmd('"hdfs namenode -format -force"'))

    def execute(self, cmd):
        return self.master.script(
                self.hadoop_user_cmd(cmd))