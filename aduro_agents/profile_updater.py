"""
Profile Updater Agent for updating user profile information in the database.

This module provides the ProfileUpdater agent which is responsible for:
- Validating and updating user profile fields
- Ensuring data integrity through validation rules
- Providing clear feedback on update operations
"""

# Standard library imports
import logging
import re
from typing import Any, Literal, TypedDict, get_args

# Third-party imports
from agents import Agent

# Local application imports
from .utils.database import DatabaseManager

logger = logging.getLogger(__name__)

# Define allowed profile fields and their validation rules
ALLOWED_FIELDS_TYPED = Literal[
    "first_name",
    "last_name",
    "city",
    "email",
    "date_of_birth",  # YYYY-MM-DD
    "dietary_preference",  # vegetarian, non-vegetarian, vegan
    "medical_conditions",
    "physical_limitations",
]

DietaryPreference = Literal["vegetarian", "non-vegetarian", "vegan"]


class FieldInfo(TypedDict):
    required: bool
    type: type | Literal["date", "email", "dietary_preference"]
    min_length: int | None
    allowed_values: list[str] | None  # For dietary_preference


ALLOWED_FIELDS: dict[ALLOWED_FIELDS_TYPED, FieldInfo] = {
    "first_name": {"required": True, "type": str, "min_length": 2, "allowed_values": None},
    "last_name": {"required": True, "type": str, "min_length": 2, "allowed_values": None},
    "city": {"required": True, "type": str, "min_length": 2, "allowed_values": None},
    "email": {"required": True, "type": "email", "min_length": None, "allowed_values": None},
    "date_of_birth": {"required": False, "type": "date", "min_length": None, "allowed_values": None},
    "dietary_preference": {
        "required": False,
        "type": "dietary_preference",
        "min_length": None,
        "allowed_values": list(get_args(DietaryPreference)),
    },
    "medical_conditions": {"required": False, "type": str, "min_length": None, "allowed_values": None},
    "physical_limitations": {"required": False, "type": str, "min_length": None, "allowed_values": None},
}


# Validation functions
def _validate_date(value: str) -> tuple[bool, str | None]:
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        return False, "Date must be in YYYY-MM-DD format."
    return True, value


def _validate_email(value: str) -> tuple[bool, str | None]:
    if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", value):
        return False, "Invalid email format."
    return True, value


def _validate_dietary_preference(value: str, allowed_values: list[str]) -> tuple[bool, str | None]:
    if value.lower() not in [v.lower() for v in allowed_values]:
        return (
            False,
            f"Invalid dietary preference. Must be one of: {', '.join(allowed_values)}."
        )
    for v_allowed in allowed_values:
        if value.lower() == v_allowed.lower():
            return True, v_allowed
    return False, "Error matching dietary preference casing."


def _validate_processed_string_value(
    field_name: str, processed_value: str, field_info: FieldInfo
) -> tuple[bool, str | None]:
    if field_info["type"] == "date":
        return _validate_date(processed_value)
    elif field_info["type"] == "email":
        return _validate_email(processed_value)
    elif field_info["type"] == "dietary_preference" and field_info["allowed_values"]:
        return _validate_dietary_preference(processed_value, field_info["allowed_values"])
    elif isinstance(field_info["type"], type) and field_info["type"] == str:
        if field_info["min_length"] is not None and len(processed_value) < field_info["min_length"]:
            return (
                False,
                f"{field_name.replace('_', ' ').capitalize()} must be at least {field_info['min_length']} characters long.",
            )
        return True, processed_value
    return True, processed_value


def validate_field_value(field_name: str, value: Any) -> tuple[bool, str | None]:
    if field_name not in ALLOWED_FIELDS:
        return False, f"Invalid field name: {field_name}"

    field_info = ALLOWED_FIELDS[field_name]

    if value is None or (isinstance(value, str) and not value.strip()):
        if field_info["required"]:
            return False, f"{field_name.replace('_', ' ').capitalize()} is required."
        return True, None

    if isinstance(value, str):
        processed_value = value.strip()
        return _validate_processed_string_value(field_name, processed_value, field_info)

    if field_info["type"] is str or field_info["type"] in ["date", "email", "dietary_preference"]:
        try:
            processed_value = str(value).strip()
            return _validate_processed_string_value(field_name, processed_value, field_info)
        except Exception:
            return False, f"Invalid data type for {field_name}. Expected a string-convertible value."
    else:
        return False, f"Invalid data type for {field_name}. Expected {field_info['type']}."


async def _perform_profile_update(
    user_id: int,
    field_name: str,
    field_value: Any,
    db_manager: DatabaseManager
) -> dict[str, Any]:
    logger.info(f"_perform_profile_update for user_id={user_id}, field='{field_name}', db_path='{db_manager.db_path}'")

    if field_name not in ALLOWED_FIELDS:
        return {"success": False, "message": f"Invalid field name: {field_name}", "field": field_name, "user_id": user_id}

    is_valid, validation_result_or_msg = validate_field_value(field_name, field_value)
    if not is_valid:
        return {"success": False, "message": validation_result_or_msg, "field": field_name, "user_id": user_id}

    validated_value = validation_result_or_msg

    try:
        if not await db_manager.user_exists(user_id):
            return {"success": False, "message": f"User with ID {user_id} not found", "field": field_name, "user_id": user_id}

        if await db_manager.update_user_profile_field(user_id, field_name, validated_value):
            return {"success": True, "message": f"Successfully updated {field_name.replace('_', ' ')} for user {user_id}", "field": field_name, "user_id": user_id, "value": validated_value}
        else:
            return {"success": False, "message": f"Database operation failed to update {field_name} for user {user_id}.", "field": field_name, "user_id": user_id}
    except Exception as e:
        logger.error(f"Exception in _perform_profile_update for user {user_id}, field {field_name}: {e!s}", exc_info=True)
        return {"success": False, "message": f"Error updating profile: {e!s}", "field": field_name, "user_id": user_id}


class ProfileUpdater(Agent):
    """Agent responsible for updating user profile information via direct Python logic."""

    def __init__(self):
        super().__init__(
            name="profile_updater",
            instructions="You are a profile update assistant. You will receive the field to update and its new value.",
            model=None,
            tools=[],
            handoff_description="Specialist for updating existing user profile details."
        )

    async def run(self, message: str, context: dict[str, Any] | None = None) -> Any:
        logger.info(f"ProfileUpdater.run called. Message: '{message}', Context: {context}")

        response_message = "An unexpected error occurred while processing your request."

        class SimpleResponse:
            def __init__(self, output_message):
                self.final_output = output_message

        if not context:
            logger.error("ProfileUpdater.run: Context is None or empty.")
            return SimpleResponse("Internal error: Agent context is missing.")

        user_id = context.get('user_id')
        field_to_update = context.get('field_to_update')
        db_manager_from_context = context.get('db_manager')
        field_value = message

        if user_id is None:
            logger.error("ProfileUpdater.run: Missing user_id in agent context.")
            response_message = "Error: User ID not specified for profile update."
        elif not field_to_update:
            logger.error("ProfileUpdater.run: Missing field_to_update in agent context.")
            response_message = "Error: Field to update not specified."
        elif not db_manager_from_context:
            logger.error("ProfileUpdater.run: db_manager not found in agent context.")
            response_message = "Internal configuration error: Database manager not available."
        else:
            logger.info(f"ProfileUpdater.run: Processing user_id='{user_id}', field_to_update='{field_to_update}', db_path='{db_manager_from_context.db_path}'")
            try:
                result_dict = await _perform_profile_update(
                    user_id=user_id,
                    field_name=field_to_update,
                    field_value=field_value,
                    db_manager=db_manager_from_context
                )
                response_message = result_dict.get("message", "Update status unclear.") # Default if message key is missing
            except Exception as e:
                logger.error(f"Exception in ProfileUpdater.run calling _perform_profile_update: {e!s}", exc_info=True)
                response_message = f"An error occurred while updating profile: {e!s}. Please contact support."

        logger.info(f"ProfileUpdater.run: Responding with: '{response_message}'")
        return SimpleResponse(response_message)


if __name__ == "__main__":
    import asyncio

    async def main():
        # Create a test database manager
        db = DatabaseManager(":memory:")

        # Create a test user
        try:
            user_id = await db.create_user_profile({
                'first_name': 'Test',
                'last_name': 'User',
                'city': 'Test City',
                'email': 'test@example.com',
                'date_of_birth': '1990-01-01'
            })

            # Example usage
            updater = ProfileUpdater()

            # Example 1: Update dietary preference with valid value
            print("\n=== Example 1: Update Dietary Preference ===")
            result = await updater.run(
                "vegetarian",
                {"user_id": user_id, "field_to_update": "dietary_preference"},
                db_manager=db
            )
            print(f"Result: {result}")

            # Verify the update
            profile = await db.get_user_profile(user_id)
            print(f"Updated profile: {profile}")

            # Example 2: Try invalid dietary preference
            print("\n=== Example 2: Invalid Dietary Preference ===")
            result = await updater.run(
                "invalid-preference",
                {"user_id": user_id, "field_to_update": "dietary_preference"},
                db_manager=db
            )
            print(f"Result: {result}")

        except Exception as e:
            print(f"Error: {e}")

    # Run the example
    asyncio.run(main())
