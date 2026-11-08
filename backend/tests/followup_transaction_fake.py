"""Transaction rollback double; real concurrent behavior is covered by Mongo integration tests."""
from copy import deepcopy


class FakeTransactionSession:
    def __init__(self, database):
        self.database = database

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def with_transaction(self, callback, **kwargs):
        snapshots = {name: deepcopy(collection.docs)
                     for name, collection in self.database.items()}
        try:
            return await callback(self)
        except BaseException:
            for name, snapshot in snapshots.items():
                self.database[name].docs = snapshot
            raise


class FakeTransactionClient:
    def __init__(self, database):
        self.database = database

    async def start_session(self):
        return FakeTransactionSession(self.database)


class FakeTransactionalDatabase(dict):
    @property
    def client(self):
        return FakeTransactionClient(self)
