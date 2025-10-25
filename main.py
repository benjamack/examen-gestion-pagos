import json
from pathlib import Path
from typing import Dict, Iterable, List

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

STATUS_REGISTRADO = "REGISTRADO"
STATUS_PAGADO = "PAGADO"
STATUS_FALLIDO = "FALLIDO"

PAYMENT_METHOD_CREDIT_CARD = "credit_card"
PAYMENT_METHOD_PAYPAL = "paypal"
SUPPORTED_PAYMENT_METHODS = {
    PAYMENT_METHOD_CREDIT_CARD,
    PAYMENT_METHOD_PAYPAL,
}

DATA_PATH = Path("data.json")

app = FastAPI(
    title="Payment Management API",
    description="API pública para gestionar el ciclo de vida de pagos online",
    version="1.0.0",
)


class Payment(BaseModel):
    payment_id: str
    amount: float
    payment_method: str
    status: str


# --- Storage helpers -----------------------------------------------------

def ensure_data_file() -> None:
    if not DATA_PATH.exists():
        DATA_PATH.write_text("{}", encoding="utf-8")


def load_all_payments() -> Dict[str, Dict]:
    ensure_data_file()
    with DATA_PATH.open("r", encoding="utf-8") as handler:
        raw = handler.read().strip() or "{}"
        return json.loads(raw)


def save_all_payments(data: Dict[str, Dict]) -> None:
    with DATA_PATH.open("w", encoding="utf-8") as handler:
        json.dump(data, handler, indent=2)


# --- Validation helpers --------------------------------------------------

def normalize_payment_method(payment_method: str) -> str:
    normalized = payment_method.lower()
    if normalized not in SUPPORTED_PAYMENT_METHODS:
        raise HTTPException(status_code=400, detail="Método de pago no soportado")
    return normalized


def credit_card_pending_conflict(all_payments: Dict[str, Dict], current_id: str) -> bool:
    return any(
        payment["payment_method"] == PAYMENT_METHOD_CREDIT_CARD
        and payment["status"] == STATUS_REGISTRADO
        and pid != current_id
        for pid, payment in all_payments.items()
    )


def ensure_credit_card_can_register(
    *, payment_id: str, all_payments: Dict[str, Dict]
) -> None:
    if credit_card_pending_conflict(all_payments, payment_id):
        raise HTTPException(
            status_code=400,
            detail="Ya existe un pago con tarjeta de crédito en estado REGISTRADO",
        )


def validate_credit_card(payment_id: str, amount: float, all_payments: Dict[str, Dict]) -> None:
    if amount >= 10_000:
        raise HTTPException(status_code=400, detail="El monto supera el límite de $10.000")
    ensure_credit_card_can_register(payment_id=payment_id, all_payments=all_payments)


def validate_paypal(amount: float) -> None:
    if amount >= 5_000:
        raise HTTPException(status_code=400, detail="El monto supera el límite de $5.000 para PayPal")


def validate_payment(payment_id: str, payment: Dict, all_payments: Dict[str, Dict]) -> None:
    method = payment["payment_method"]
    amount = payment["amount"]
    if method == PAYMENT_METHOD_CREDIT_CARD:
        validate_credit_card(payment_id, amount, all_payments)
    elif method == PAYMENT_METHOD_PAYPAL:
        validate_paypal(amount)
    else:
        raise HTTPException(status_code=400, detail="Método de pago no soportado")


# --- API helpers ---------------------------------------------------------

def serialize_payments(payments: Iterable[tuple[str, Dict]]) -> List[Payment]:
    return [Payment(payment_id=pid, **data) for pid, data in payments]


def get_payment_or_404(payment_id: str, data: Dict[str, Dict]) -> Dict:
    try:
        return data[payment_id]
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Pago no encontrado") from exc


# --- Endpoints -----------------------------------------------------------


@app.get("/payments", response_model=List[Payment])
def list_payments() -> List[Payment]:
    data = load_all_payments()
    return serialize_payments(data.items())


@app.post("/payments/{payment_id}", response_model=Payment, status_code=201)
def register_payment(
    payment_id: str,
    amount: float = Query(..., gt=0, description="Monto del pago"),
    payment_method: str = Query(..., description="Método de pago"),
) -> Payment:
    data = load_all_payments()
    if payment_id in data:
        raise HTTPException(status_code=409, detail="El pago ya existe")

    normalized_method = normalize_payment_method(payment_method)
    if normalized_method == PAYMENT_METHOD_CREDIT_CARD:
        ensure_credit_card_can_register(payment_id=payment_id, all_payments=data)

    payment = {
        "amount": amount,
        "payment_method": normalized_method,
        "status": STATUS_REGISTRADO,
    }
    data[payment_id] = payment
    save_all_payments(data)
    return Payment(payment_id=payment_id, **payment)


@app.post("/payments/{payment_id}/update", response_model=Payment)
def update_payment(
    payment_id: str,
    amount: float = Query(..., gt=0, description="Nuevo monto del pago"),
    payment_method: str = Query(..., description="Nuevo método de pago"),
) -> Payment:
    data = load_all_payments()
    payment = get_payment_or_404(payment_id, data)
    if payment["status"] != STATUS_REGISTRADO:
        raise HTTPException(status_code=400, detail="Solo se pueden actualizar pagos en estado REGISTRADO")

    normalized_method = normalize_payment_method(payment_method)
    payment.update({
        "amount": amount,
        "payment_method": normalized_method,
    })

    if normalized_method == PAYMENT_METHOD_CREDIT_CARD:
        ensure_credit_card_can_register(payment_id=payment_id, all_payments=data)

    data[payment_id] = payment
    save_all_payments(data)
    return Payment(payment_id=payment_id, **payment)


@app.post("/payments/{payment_id}/pay", response_model=Payment)
def pay_payment(payment_id: str) -> Payment:
    data = load_all_payments()
    payment = get_payment_or_404(payment_id, data)
    if payment["status"] != STATUS_REGISTRADO:
        raise HTTPException(status_code=400, detail="Solo se pueden pagar pagos en estado REGISTRADO")

    try:
        validate_payment(payment_id, payment, data)
    except HTTPException:
        payment["status"] = STATUS_FALLIDO
        data[payment_id] = payment
        save_all_payments(data)
        raise

    payment["status"] = STATUS_PAGADO
    data[payment_id] = payment
    save_all_payments(data)
    return Payment(payment_id=payment_id, **payment)


@app.post("/payments/{payment_id}/revert", response_model=Payment)
def revert_payment(payment_id: str) -> Payment:
    data = load_all_payments()
    payment = get_payment_or_404(payment_id, data)
    if payment["status"] != STATUS_FALLIDO:
        raise HTTPException(status_code=400, detail="Solo se pueden revertir pagos FALLIDOS")

    payment["status"] = STATUS_REGISTRADO
    data[payment_id] = payment
    save_all_payments(data)
    return Payment(payment_id=payment_id, **payment)
