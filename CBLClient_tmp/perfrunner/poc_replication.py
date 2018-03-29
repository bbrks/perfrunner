
import time

from CBLClient.Database import Database

from CBLClient.Replication import Replication
from CBLClient.Authenticator import Authenticator
from CBLClient.keywords.MobileRestClient import MobileRestClient


cbl_db_name = "cbl_db"
cbl_url = "http://10.17.0.129:8080"
replicator_authenticator_type = "session"
sg_url = "http://172.23.100.204:4985"
sg_db_name = "db"
sg_blip_url = "ws://172.23.100.204:4984/{}".format(sg_db_name)
channels = ["ABC"]
replication_type = "push"

db = Database(cbl_url)
db_config = db.configure() #def configure(self, directory=None, conflictResolver=None, password=None):
cbl_db = db.create(cbl_db_name, db_config)
db.create_bulk_docs(number=10000, id_prefix="poc3", db=cbl_db, channels=channels)
cbl_added_doc_ids = db.getDocIds(cbl_db)
print("Added docs to CBL: {}".format(cbl_added_doc_ids))

sg_client = MobileRestClient()
sg_client.create_user(sg_url, sg_db_name, "autotest", password="password", channels=["ABC"])
cookie, session = sg_client.create_session("http://172.23.100.204:4985", "db", "autotest", "password")
auth_session = cookie, session
sync_cookie = "{}={}".format(cookie, session)
session_header = {"Cookie": sync_cookie}

# Start and stop continuous replication
replicator = Replication(cbl_url)
authenticator = Authenticator(cbl_url)
if replicator_authenticator_type == "session":
    replicator_authenticator = authenticator.authentication(session, cookie, authentication_type="session")
elif replicator_authenticator_type == "basic":
    replicator_authenticator = authenticator.authentication(username="autotest", password="password",
                                                            authentication_type="basic")
else:
    replicator_authenticator = None

print("Configuring replicator")
repl_config = replicator.configure(cbl_db, target_url=sg_blip_url, replication_type=replication_type, continuous=True,
                                   replicator_authenticator=replicator_authenticator, headers=session_header,
                                   documentIDs=cbl_added_doc_ids)
repl = replicator.create(repl_config)
print("Starting replicator")
replicator.start(repl)
print("Waiting for replicator to go idle")
replicator.wait_until_replicator_idle(repl)
replicator.stop(repl)
