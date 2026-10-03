from datetime import datetime, timezone
from fastapi import status
from sqlalchemy.exc import IntegrityError
from sqlmodel import select, Session
from uuid import UUID

from src.api.models.base import CreditErrorResponse, ErrorResponse
from src.api.models.exc import AppException
from src.const import CURRENT_CREDIT_POLICY_VERSION, CREDIT_POLICY_VERSIONS, CreditFeature
from src.db.db import engine
from src.db.models import CreditLedger, CreditReservation, UserCreditAccount
from src.enums import CreditReservationStatus, ErrorResponseCode

def reserve(
    user_id: UUID,
    feature: CreditFeature,
    idempotency_key: str,
    metadata: dict[str, str] | None = None,
) -> CreditReservation | None:
    with Session(engine) as session:
        decrease_amount = CREDIT_POLICY_VERSIONS[CURRENT_CREDIT_POLICY_VERSION][feature]
        if decrease_amount <= 0:
            return None

        existing_reservation = session.exec(
            select(CreditReservation).where(CreditReservation.idempotency_key == idempotency_key)
        ).first()
        if existing_reservation:
            if (
                existing_reservation.user_id != user_id
                or existing_reservation.feature != feature
                or existing_reservation.amount != decrease_amount
            ):
                raise AppException(
                    status_code=status.HTTP_409_CONFLICT,
                    error=ErrorResponse(
                        code=ErrorResponseCode.IDEMPOTENCY_KEY_MISMATCH,
                        message="Idempotency key payload mismatch",
                    ),
                )
            return existing_reservation

        account = session.exec(
            select(UserCreditAccount).where(UserCreditAccount.user_id == user_id).with_for_update()
        ).first()

        available = (account.balance - account.reserved) if account else 0
        if not account or available < decrease_amount:
            raise AppException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                error=CreditErrorResponse(
                    code = ErrorResponseCode.INSUFFICIENT_CREDITS,
                    message = "Insufficient credits for the requested feature",
                    feature=feature,
                    required=decrease_amount,
                    available=max(available, 0),
                    policy_version=CURRENT_CREDIT_POLICY_VERSION,
                )
            )

        account.reserved += decrease_amount

        reservation = CreditReservation(
            user_id=user_id,
            amount=decrease_amount,
            status=CreditReservationStatus.RESERVED,
            feature=feature,
            policy_version=CURRENT_CREDIT_POLICY_VERSION,
            idempotency_key=idempotency_key,
            meta_data=metadata,
        )
        session.add(account)
        session.add(reservation)
        try:
            session.commit()
            session.refresh(reservation)
            return reservation
        except IntegrityError:
            session.rollback()
            concurrent_reservation = session.exec(
                select(CreditReservation).where(CreditReservation.idempotency_key == idempotency_key)
            ).first()
            if concurrent_reservation:
                if (
                    concurrent_reservation.user_id != user_id
                    or concurrent_reservation.feature != feature
                    or concurrent_reservation.amount != decrease_amount
                ):
                    raise AppException(
                        status_code=status.HTTP_409_CONFLICT,
                        error=ErrorResponse(
                            code=ErrorResponseCode.IDEMPOTENCY_KEY_MISMATCH,
                            message="Idempotency key payload mismatch",
                        ),
                    )
                return concurrent_reservation
            raise

def capture(
    reservation_id: UUID,
    session: Session,
    actor_id: UUID,
) -> CreditReservation:
    reservation = session.exec(
        select(CreditReservation)
        .where(CreditReservation.id == reservation_id)
        .with_for_update()
    ).first()

    if not reservation:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            error=ErrorResponse(
                code=ErrorResponseCode.NOT_FOUND,
                message="Credit reservation not found",
            ),
        )

    if reservation.status == CreditReservationStatus.CAPTURED:
        return reservation

    if reservation.status != CreditReservationStatus.RESERVED:
        raise AppException(
            status_code=status.HTTP_409_CONFLICT,
            error=ErrorResponse(
                code=ErrorResponseCode.INVALID_OPERATION,
                message=f"Cannot capture reservation in status {reservation.status}",
            ),
        )

    account = session.exec(
        select(UserCreditAccount)
        .where(UserCreditAccount.user_id == reservation.user_id)
        .with_for_update()
    ).first()
    if not account:
        raise AppException(
            status_code=status.HTTP_404_NOT_FOUND,
            error=ErrorResponse(
                code=ErrorResponseCode.NOT_FOUND,
                message="User credit account not found",
            ),
        )

    account.reserved -= reservation.amount
    account.balance -= reservation.amount

    reservation.status = CreditReservationStatus.CAPTURED
    reservation.finished_at = datetime.now(timezone.utc)

    ledger = CreditLedger(
        user_id=reservation.user_id,
        amount=-reservation.amount,
        balance_after=account.balance,
        reason=f"Capture reservation {reservation.id}",
        feature=reservation.feature,
        policy_version=reservation.policy_version,
        idempotency_key=f"capture:{reservation.id}",
        reference_type="RESERVATION",
        reference_id=str(reservation.id),
        actor_id=actor_id,
    )

    session.add(account)
    session.add(reservation)
    session.add(ledger)
    session.flush()
    return reservation

def release(reservation_id: UUID) -> CreditReservation | None:
    with Session(engine) as session:
        reservation = session.exec(
            select(CreditReservation)
            .where(CreditReservation.id == reservation_id)
            .with_for_update()
        ).first()

        if not reservation:
            return None

        if reservation.status == CreditReservationStatus.RELEASED:
            return reservation

        if reservation.status != CreditReservationStatus.RESERVED:
            return reservation

        account = session.exec(
            select(UserCreditAccount)
            .where(UserCreditAccount.user_id == reservation.user_id)
            .with_for_update()
        ).first()

        if account:
            account.reserved -= reservation.amount
            session.add(account)

        reservation.status = CreditReservationStatus.RELEASED
        reservation.finished_at = datetime.now(timezone.utc)
        session.add(reservation)

        session.commit()
        session.refresh(reservation)
        return reservation

def grant(
    user_id: UUID,
    amount: int,
    reason: str,
    idempotency_key: str,
    actor_id: UUID,
) -> CreditLedger:
    if amount <= 0:
        raise AppException(
            status_code=status.HTTP_400_BAD_REQUEST,
            error=ErrorResponse(
                code=ErrorResponseCode.BAD_REQUEST,
                message="Grant amount must be greater than zero",
            ),
        )

    with Session(engine) as session:
        existing_ledger = session.exec(
            select(CreditLedger).where(CreditLedger.idempotency_key == idempotency_key)
        ).first()
        if existing_ledger:
            if existing_ledger.user_id != user_id or existing_ledger.amount != amount:
                raise AppException(
                    status_code=status.HTTP_409_CONFLICT,
                    error=ErrorResponse(
                        code=ErrorResponseCode.IDEMPOTENCY_KEY_MISMATCH,
                        message="Idempotency key payload mismatch",
                    ),
                )
            return existing_ledger

        account = session.exec(
            select(UserCreditAccount)
            .where(UserCreditAccount.user_id == user_id)
            .with_for_update()
        ).first()

        if not account:
            account = UserCreditAccount(user_id=user_id, balance=0, reserved=0)
            session.add(account)
            session.flush()

        account.balance += amount

        ledger = CreditLedger(
            user_id=user_id,
            amount=amount,
            balance_after=account.balance,
            reason=reason,
            feature=None,
            policy_version=CURRENT_CREDIT_POLICY_VERSION,
            idempotency_key=idempotency_key,
            reference_type="GRANT",
            reference_id=None,
            actor_id=actor_id,
        )

        session.add(account)
        session.add(ledger)

        try:
            session.commit()
            session.refresh(ledger)
            return ledger
        except IntegrityError:
            session.rollback()
            concurrent_ledger = session.exec(
                select(CreditLedger).where(CreditLedger.idempotency_key == idempotency_key)
            ).first()
            if concurrent_ledger:
                if concurrent_ledger.user_id != user_id or concurrent_ledger.amount != amount:
                    raise AppException(
                        status_code=status.HTTP_409_CONFLICT,
                        error=ErrorResponse(
                            code=ErrorResponseCode.IDEMPOTENCY_KEY_MISMATCH,
                            message="Idempotency key payload mismatch",
                        ),
                    )
                return concurrent_ledger
            raise