# API de Gestión de Pagos

API construida con FastAPI para el examen de Ingeniería de Software. Expone endpoints que permiten registrar, pagar, actualizar y revertir pagos persistidos en un archivo JSON simple.

## Requisitos

- Python 3.11+
- Dependencias listadas en `requirements.txt`

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Ejecución del servidor

```bash
uvicorn main:app --reload
```
La API se accede mediante el siguiente puerto http://127.0.0.1:8000/docs.

## Pruebas automatizadas

```bash
pytest
```

Los tests cubren el flujo completo de un pago con tarjeta de crédito, los límites de PayPal y la restricción de exclusividad para pagos con tarjeta en estado `REGISTRADO`.

## Endpoints

| Método | Endpoint | Descripción |
| --- | --- | --- |
| GET | `/payments` | Lista todos los pagos con su estado actual. |
| POST | `/payments/{payment_id}` | Registra un pago. Recibe `amount` y `payment_method` (query). |
| POST | `/payments/{payment_id}/update` | Actualiza monto y método si el pago sigue `REGISTRADO`. |
| POST | `/payments/{payment_id}/pay` | Ejecuta la validación y marca el pago como `PAGADO` o `FALLIDO`. |
| POST | `/payments/{payment_id}/revert` | Permite volver un pago `FALLIDO` a `REGISTRADO`. |
| POST | `/payments/{payment_id}/cancel` | Marca un pago `REGISTRADO` como `CANCELADO`. |

`payment_method` acepta `credit_card` o `paypal` (case insensitive).

## Lógica de validación implementada

- **Tarjeta de crédito**: el monto debe ser menor a $10.000 y no puede existir otro pago con tarjeta en estado `REGISTRADO`.
- **PayPal**: el monto debe ser menor a $5.000.
- Si la validación falla el pago pasa a `FALLIDO` y la API responde 400 con el motivo.
- Solo se pueden modificar pagos en `REGISTRADO`. Solo se pueden pagar pagos en `REGISTRADO`. Solo se pueden revertir pagos en `FALLIDO`. Los pagos `REGISTRADO` también pueden pasar a `CANCELADO`, estado final que no admite otras transiciones.

## Decisiones de diseño y supuestos

1. **Persistencia mínima**: se usa `data.json` como almacén plano para simplificar la evaluación. Los helpers normalizan su existencia y guardan los cambios con `indent=2` para facilitar inspección manual.
2. **Normalización de métodos de pago**: todos los métodos se almacenan en minúsculas para evitar duplicados lógicos por casing distinto.
3. **Validación en el momento del pago**: las reglas de negocio se aplican cuando se invoca `/pay`, tal como indica el flujo del enunciado. No obstante, la restricción de exclusividad de tarjeta de crédito también se comprueba al registrar/actualizar para evitar estados inválidos.
4. **Estados explícitos**: se modelan los estados `REGISTRADO`, `PAGADO`, `FALLIDO` y `CANCELADO` como constantes para compartirlos entre la API y los tests.
5. **Supuesto de trabajo en equipo**: se documenta cómo correr el servidor y las pruebas para que pueda integrarse en un pipeline de CI/CD o revisarse mediante PRs.

## Patrones de diseño utilizados

- **Data Transfer Object (DTO)**: `Payment` (modelo Pydantic) encapsula la representación expuesta por la API y asegura validaciones de formato consistentes.
- **Repositorio liviano**: los helpers `load_all_payments` y `save_all_payments` concentran el acceso a `data.json`, aislando al resto de la lógica de la persistencia.
- **Estrategia por método de pago**: `validate_payment` delega en `validate_credit_card` y `validate_paypal`, manteniendo separadas las reglas de negocio por canal.
