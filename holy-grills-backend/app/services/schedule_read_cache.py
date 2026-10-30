"""Request-local configuration snapshots for the multi-day calendar.

Orders stay live reads. No cross-request cache, writes or shared user state.
"""
import copy


class ScheduleReadCache:
    TABLES = {'ordering_windows', 'operating_hour_overrides', 'delivery_windows', 'operating_hours', 'kitchen_settings'}

    def __init__(self, db, campus_id):
        self.db, self.campus_id, self.rows = db, campus_id, {}

    def table(self, name):
        if name not in self.TABLES:
            return self.db.table(name)
        if name not in self.rows:
            query = self.db.table(name).select('*')
            if name in {'operating_hour_overrides', 'operating_hours'}:
                query = query.or_(f'campus_id.eq.{self.campus_id},campus_id.is.null')
            else:
                query = query.eq('campus_id', self.campus_id)
            self.rows[name] = query.execute() or []
        return _Rows(copy.deepcopy(self.rows[name]))


class _Rows:
    def __init__(self, rows):
        self.rows, self.one = rows, False

    def select(self, *args): return self

    def eq(self, key, value):
        self.rows = [row for row in self.rows if str(row.get(key)) == str(value)]
        return self

    def is_(self, key, value):
        if value == 'null' or value is None:
            self.rows = [row for row in self.rows if row.get(key) is None]
        return self

    def single(self):
        self.one = True
        return self

    def execute(self):
        return (self.rows[0] if self.rows else None) if self.one else self.rows
