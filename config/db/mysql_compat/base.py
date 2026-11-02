"""Backend MySQL que acepta MariaDB 10.4 (la que trae XAMPP).

Django 5.x exige MariaDB 10.5+. Lo único de 10.5 que usa es
INSERT ... RETURNING, así que se desactiva en versiones anteriores.
En producción se recomienda MySQL 8 / MariaDB 10.6+.
"""

from django.db.backends.mysql import base, features
from django.utils.functional import cached_property


class DatabaseFeatures(features.DatabaseFeatures):
    @cached_property
    def minimum_database_version(self):
        if self.connection.mysql_is_mariadb:
            return (10, 4)
        return (8, 0, 11)

    @cached_property
    def _mariadb_con_returning(self):
        return self.connection.mysql_is_mariadb and self.connection.mysql_version >= (10, 5)

    @cached_property
    def can_return_columns_from_insert(self):
        return self._mariadb_con_returning

    @cached_property
    def can_return_rows_from_bulk_insert(self):
        return self._mariadb_con_returning


class DatabaseWrapper(base.DatabaseWrapper):
    features_class = DatabaseFeatures
