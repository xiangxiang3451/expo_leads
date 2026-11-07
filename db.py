import sqlite3
from pathlib import Path

import click
from flask import current_app, g
from flask.cli import with_appcontext


def get_db():
    """在当前请求中获取数据库连接。"""
    if "db" not in g:
        g.db = sqlite3.connect(
            current_app.config["DATABASE"],
            timeout=10,
        )
        g.db.row_factory = sqlite3.Row

    return g.db


def close_db(error=None):
    """请求结束后关闭连接。"""
    connection = g.pop("db", None)

    if connection is not None:
        connection.close()


def init_db():
    """根据 schema.sql 创建数据表。"""
    database_path = Path(current_app.config["DATABASE"])
    database_path.parent.mkdir(parents=True, exist_ok=True)

    with current_app.open_resource("schema.sql") as file:
        get_db().executescript(file.read().decode("utf-8"))


@click.command("init-db")
@with_appcontext
def init_db_command():
    init_db()
    click.echo("数据库初始化完成。")


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)