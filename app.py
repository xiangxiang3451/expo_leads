from flask import Flask, abort, render_template

app = Flask(__name__)

DEMO_LEADS = {
    1: {
        "company": "Нева Авто",
        "contact": "Алексей",
        "product": "耐油橡胶密封圈，希望周五前收到报价。",
        "status": "pending",
    },
    2: {
        "company": "Балтик Деталь",
        "contact": "Мария",
        "product": "汽车减震胶套，希望先确认样品规格。",
        "status": "contacted",
    },
    3: {
        "company": "Север Поставка",
        "contact": "Иван",
        "product": "工业橡胶垫片，已发送首批采购报价。",
        "status": "quoted",
    },
}


@app.route("/")
def leads_page():
    return render_template("leads.html", leads=DEMO_LEADS)


@app.route("/leads/<int:lead_id>/edit")
def edit_lead_page(lead_id):
    lead = DEMO_LEADS.get(lead_id)
    if lead is None:
        abort(404)

    return render_template("lead_edit.html", lead=lead)


if __name__ == "__main__":
    app.run()