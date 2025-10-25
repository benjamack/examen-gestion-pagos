import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import main


def setup_temp_store(tmp_path, monkeypatch):
    tmp_file = tmp_path / "data.json"
    tmp_file.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(main, "DATA_PATH", tmp_file)
    return tmp_file


def read_raw_data(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_credit_card_flow(tmp_path, monkeypatch):
    data_file = setup_temp_store(tmp_path, monkeypatch)

    payment = main.register_payment(
        payment_id="pay-1", amount=100.5, payment_method="credit_card"
    )
    assert payment.status == main.STATUS_REGISTRADO

    paid = main.pay_payment(payment_id="pay-1")
    assert paid.status == main.STATUS_PAGADO

    listed = main.list_payments()
    assert len(listed) == 1
    assert listed[0].status == main.STATUS_PAGADO

    payload = read_raw_data(data_file)
    assert payload["pay-1"]["status"] == main.STATUS_PAGADO


def test_paypal_validation_and_revert(tmp_path, monkeypatch):
    data_file = setup_temp_store(tmp_path, monkeypatch)

    payment = main.register_payment(
        payment_id="pay-2", amount=6000, payment_method="paypal"
    )
    assert payment.status == main.STATUS_REGISTRADO

    with pytest.raises(main.HTTPException):
        main.pay_payment(payment_id="pay-2")

    stored = read_raw_data(data_file)
    assert stored["pay-2"]["status"] == main.STATUS_FALLIDO

    reverted = main.revert_payment(payment_id="pay-2")
    assert reverted.status == main.STATUS_REGISTRADO

    updated = main.update_payment(
        payment_id="pay-2", amount=2000, payment_method="paypal"
    )
    assert updated.amount == 2000

    paid = main.pay_payment(payment_id="pay-2")
    assert paid.status == main.STATUS_PAGADO


def test_credit_card_pending_constraint(tmp_path, monkeypatch):
    setup_temp_store(tmp_path, monkeypatch)

    main.register_payment(
        payment_id="pay-cc-1", amount=100, payment_method="credit_card"
    )

    with pytest.raises(main.HTTPException):
        main.register_payment(
            payment_id="pay-cc-2", amount=50, payment_method="credit_card"
        )

    main.pay_payment(payment_id="pay-cc-1")

    second = main.register_payment(
        payment_id="pay-cc-2", amount=50, payment_method="credit_card"
    )
    assert second.status == main.STATUS_REGISTRADO
