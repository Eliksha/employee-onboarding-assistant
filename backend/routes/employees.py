
"""Employee-specific API endpoints.

Authorization: every /employees/{employee_id}/... route only serves the signed-in employee's own
records (403 otherwise); state-changing routes also require the session CSRF token.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from backend.security import current_user, own_employee_read, own_employee_write
from backend.services import employee_db

router = APIRouter(prefix="/employees", tags=["Employees"])


def require_employee(employee_id: str) -> dict:
    """Validate that a fictional demo employee exists."""
    employee = employee_db.get_employee(employee_id)

    if employee is None:
        raise HTTPException(
            status_code=404,
            detail="Employee not found",
        )

    return employee


# --------------------------------------------------
# Employee Profile
# --------------------------------------------------

@router.get("/{employee_id}", dependencies=[Depends(own_employee_read)])
def get_employee(employee_id: str):
    return require_employee(employee_id)


# --------------------------------------------------
# Employee Leave Balances
# --------------------------------------------------

@router.get("/{employee_id}/leave-balances", dependencies=[Depends(own_employee_read)])
def get_leave_balances(employee_id: str):
    require_employee(employee_id)
    return employee_db.get_leave_balances(employee_id)


# --------------------------------------------------
# Employee IT Assets
# --------------------------------------------------

@router.get("/{employee_id}/assets", dependencies=[Depends(own_employee_read)])
def get_assets(employee_id: str):
    require_employee(employee_id)
    return employee_db.get_employee_assets(employee_id)


# --------------------------------------------------
# Employee Onboarding Checklist
# --------------------------------------------------

@router.get("/{employee_id}/checklist", dependencies=[Depends(own_employee_read)])
def get_checklist(employee_id: str):
    require_employee(employee_id)
    return employee_db.get_employee_checklist(employee_id)


class EmployeeChecklistUpdate(BaseModel):
    done: bool


@router.patch("/{employee_id}/checklist/{item_id}", dependencies=[Depends(own_employee_write)])
def update_employee_checklist(
    employee_id: str,
    item_id: int,
    body: EmployeeChecklistUpdate,
):
    require_employee(employee_id)

    updated_item = employee_db.update_employee_checklist(
        employee_id=employee_id,
        item_id=item_id,
        done=body.done,
    )

    if updated_item is None:
        raise HTTPException(
            status_code=404,
            detail="Checklist item not found for this employee",
        )

    return updated_item


# --------------------------------------------------
# Employee Support Tickets
# --------------------------------------------------

@router.get("/{employee_id}/tickets", dependencies=[Depends(own_employee_read)])
def get_tickets(employee_id: str):
    require_employee(employee_id)
    return employee_db.get_employee_tickets(employee_id)


class EmployeeTicketCreate(BaseModel):
    category: str = Field(min_length=2, max_length=50)
    subject: str = Field(min_length=3, max_length=150)
    description: str = Field(min_length=5, max_length=2000)

    @field_validator(
        "category",
        "subject",
        "description",
        mode="before",
    )
    @classmethod
    def validate_text(cls, value):
        """Remove surrounding whitespace and reject empty inputs."""
        if not isinstance(value, str):
            raise ValueError("Must be a valid text value")

        value = value.strip()

        if not value:
            raise ValueError(
                "Field cannot be empty or whitespace"
            )

        return value


@router.post("/{employee_id}/tickets", status_code=201, dependencies=[Depends(own_employee_write)])
def create_employee_ticket(
    employee_id: str,
    body: EmployeeTicketCreate,
):
    require_employee(employee_id)

    return employee_db.create_employee_ticket(
        employee_id=employee_id,
        category=body.category,
        subject=body.subject,
        description=body.description,
    )


# --------------------------------------------------
# Payroll Calendar
# --------------------------------------------------

@router.get("/payroll/calendar", dependencies=[Depends(current_user)])
def get_payroll_calendar():
    return employee_db.get_payroll_calendar()
