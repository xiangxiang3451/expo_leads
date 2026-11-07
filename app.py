import os
from pathlib import Path

from dotenv import load_dotenv
from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_wtf.csrf import CSRFProtect

import db


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

app = Flask(__name__)

app.config.update(
    SECRET_KEY=os.getenv("SECRET_KEY"),
    DATABASE=str(BASE_DIR / "data" / "leads.sqlite3"),
)

if not app.config["SECRET_KEY"]:
    raise RuntimeError("请先在项目根目录的 .env 中设置 SECRET_KEY。")

CSRFProtect(app)
db.init_app(app)

STATUS_LABELS = {
    "pending": "待联系",
    "contacted": "已联系",
    "quoted": "已报价",
}


@app.context_processor
def template_variables():
    """向所有模板提供状态名称。"""
    return {"status_labels": STATUS_LABELS}


def get_lead_or_404(lead_id):
    """查询单条线索，找不到时返回 404。"""
    lead = db.get_db().execute(
        "SELECT * FROM leads WHERE id = ?",
        (lead_id,),
    ).fetchone()

    if lead is None:
        abort(404)

    return lead


def read_lead_form():
    """读取并校验新增、编辑表单。"""
    lead = {}
    errors = []

    for field, label, limit in (
        ("company", "公司名称", 200),
        ("contact", "联系人", 200),
        ("product", "产品需求", 2000),
    ):
        value = request.form.get(field, "").strip()
        lead[field] = value

        if not value:
            errors.append(f"请填写{label}。")
        elif len(value) > limit:
            errors.append(f"{label}最多填写 {limit} 个字符。")

    lead["status"] = request.form.get("status", "")

    if lead["status"] not in STATUS_LABELS:
        errors.append("请选择有效的跟进状态。")

    return lead, errors


@app.get("/")
def leads_page():
    """显示列表，按产品需求和状态进行组合筛选。"""
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "")

    if status and status not in STATUS_LABELS:
        abort(400, description="跟进状态无效。")

    connection = db.get_db()

    leads = connection.execute(
        """
        SELECT * FROM leads
        WHERE instr(product, ?) > 0
          AND (? = '' OR status = ?)
        ORDER BY id DESC
        """,
        (q, status, status),
    ).fetchall()

    # 统计全部线索的状态数量。
    counts = {value: 0 for value in STATUS_LABELS}

    rows = connection.execute(
        """
        SELECT status, COUNT(*) AS amount
        FROM leads
        GROUP BY status
        """
    ).fetchall()

    for row in rows:
        counts[row["status"]] = row["amount"]

    counts["total"] = sum(counts.values())

    return render_template(
        "leads.html",
        leads=leads,
        counts=counts,
        q=q,
        selected_status=status,
    )


@app.route("/leads/new", methods=["GET", "POST"])
def create_lead_page():
    """显示新增表单，并保存新线索。"""
    lead = {
        "company": "",
        "contact": "",
        "product": "",
        "status": "pending",
    }
    errors = []

    if request.method == "POST":
        lead, errors = read_lead_form()

        if not errors:
            with db.get_db() as connection:
                connection.execute(
                    """
                    INSERT INTO leads (company, contact, product, status)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        lead["company"],
                        lead["contact"],
                        lead["product"],
                        lead["status"],
                    ),
                )

            flash("客户线索已新增。", "success")
            return redirect(url_for("leads_page"), code=303)

    return render_template(
        "lead_edit.html",
        lead=lead,
        errors=errors,
        title="新增客户线索",
    ), (400 if errors else 200)


@app.route("/leads/<int:lead_id>/edit", methods=["GET", "POST"])
def edit_lead_page(lead_id):
    """显示编辑表单，并更新线索。"""
    lead = get_lead_or_404(lead_id)
    errors = []

    if request.method == "POST":
        lead, errors = read_lead_form()

        if not errors:
            with db.get_db() as connection:
                cursor = connection.execute(
                    """
                    UPDATE leads
                    SET company = ?,
                        contact = ?,
                        product = ?,
                        status = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (
                        lead["company"],
                        lead["contact"],
                        lead["product"],
                        lead["status"],
                        lead_id,
                    ),
                )

                if cursor.rowcount == 0:
                    abort(404)

            flash("客户线索已更新。", "success")
            return redirect(url_for("leads_page"), code=303)

    return render_template(
        "lead_edit.html",
        lead=lead,
        errors=errors,
        title="编辑客户线索",
    ), (400 if errors else 200)


@app.post("/leads/<int:lead_id>/delete")
def delete_lead(lead_id):
    """删除指定线索。"""
    with db.get_db() as connection:
        cursor = connection.execute(
            "DELETE FROM leads WHERE id = ?",
            (lead_id,),
        )

        if cursor.rowcount == 0:
            abort(404)

    flash("客户线索已删除。", "success")
    return redirect(url_for("leads_page"), code=303)


if __name__ == "__main__":
    app.run()