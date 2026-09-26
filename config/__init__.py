"""Ratshie configuration package."""
try:
    import pymysql

    pymysql.install_as_MySQLdb()
except ImportError:  # pragma: no cover - local dev without the MySQL driver
    pass