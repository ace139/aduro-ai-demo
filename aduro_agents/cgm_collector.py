"""
CGM-Collector Agent for collecting and storing CGM readings.
"""

import re
from datetime import datetime, time
from typing import Any

from agents import Agent, function_tool

from aduro_agents.utils.database import DatabaseManager

# Constants
MAX_RETRIES = 2
READING_PATTERN = r'^\s*\d+\s*(?:,\s*\d+\s*)*$'  # Pattern for validating CGM readings input (comma-separated numbers with optional spaces)

# Meal time ranges (in 24-hour format)
MEAL_TIMES = {
    "breakfast": (time(6, 0), time(10, 59)),   # 6:00 AM - 10:59 AM
    "lunch": (time(11, 0), time(15, 59)),     # 11:00 AM - 3:59 PM
    "dinner": (time(16, 0), time(21, 59))     # 4:00 PM - 9:59 PM
}

def _infer_reading_type(timestamp: datetime) -> str:
    """
    Infer the meal type based on the time of day.

    Args:
        timestamp: The datetime to check

    Returns:
        str: The inferred meal type (breakfast, lunch, dinner, or snack)
    """
    current_time = timestamp.time()

    # Check each meal time range
    for meal, (start, end) in MEAL_TIMES.items():
        if start <= current_time <= end:
            return meal

    # Default to snack for times outside defined meal periods
    return "snack"

@function_tool
async def insert_cgm_reading(
    user_id: int,
    glucose_value: float,
    timestamp: str | None = None,
    meal_context: str | None = None,
) -> str:
    """Insert a CGM reading into the database.

    Args:
        user_id: The ID of the user
        glucose_value: The glucose value in mg/dL
        timestamp: Optional timestamp in ISO format (defaults to current time)
        meal_context: Optional context about the meal (e.g., 'before meal', 'after meal')

    Returns:
        str: Success or error message
    """
    db_manager = DatabaseManager()

    try:
        # Validate glucose value
        if not isinstance(glucose_value, int | float):
            return "Error: Glucose value must be a number"

        if not 0 <= glucose_value <= 1000:
            return "Error: Glucose value must be between 0 and 1000 mg/dL"

        # Parse timestamp if provided, otherwise use current time
        if timestamp is not None:
            try:
                timestamp_dt = datetime.fromisoformat(timestamp)
            except (ValueError, TypeError):
                return "Error: Invalid timestamp format. Use ISO format (e.g., '2023-01-01T12:00:00')"
        else:
            timestamp_dt = datetime.utcnow()

        # Prepare reading data
        reading_data = {"value": float(glucose_value), "timestamp": timestamp_dt}
        if meal_context:
            reading_data["meal_context"] = meal_context

        # Insert reading
        success = await db_manager.insert_cgm_readings(
            user_id=user_id,
            readings=[reading_data]
        )

        if success:
            return "Successfully stored CGM reading"
        return "Failed to store CGM reading"
    except Exception as e:
        return f"Error storing CGM reading: {e!s}"

class CGMCollector(Agent):
    """Agent for collecting and storing CGM readings."""

    def __init__(self):
        instructions = """
        You are a clinical CGM (Continuous Glucose Monitor) data ingestion assistant. Your primary role is to receive a blood glucose reading, attempt to process it, and store it using the 'insert_cgm_reading' tool.

        Here's your workflow:
        1. The user's blood glucose reading will be provided as the main 'message' input to you.
        2. The 'user_id' (integer) will be available in the 'context' provided to your run.

        Processing the reading:
        3. First, you MUST attempt to convert the input 'message' (the glucose reading) into a floating-point number (e.g., 120.5 or 85).
           - If the 'message' cannot be converted to a number (e.g., it's text like 'abc' or 'high'), you should respond to the user indicating that the format is invalid and a numerical value is expected. Do NOT call the tool in this case.
        4. If the 'message' is successfully converted to a number (the 'glucose_value'):
           - Call the 'insert_cgm_reading' tool. You must provide the 'user_id' and the numerical 'glucose_value'. You generally do not need to provide 'timestamp' or 'meal_context' for simple readings unless explicitly instructed otherwise for a specific interaction.

        After calling the tool (if successful type conversion):
        - The 'insert_cgm_reading' tool will return a string message (e.g., 'Successfully stored CGM reading' or 'Failed to store CGM reading' or an error message).
        - Relay this message directly to the user.

        Be concise and professional. Your goal is a single, successful attempt to log the provided reading or give clear feedback if the format is wrong.
        """
        super().__init__(
            name="cgm_collector",
            instructions=instructions,
            model="gpt-4.1-mini",
            tools=[insert_cgm_reading],
            handoff_description="Specialist for collecting and recording CGM (Continuous Glucose Monitor) readings."
        )
        self.retry_count = 0 # This attribute is part of the class but not used by the current process_input logic relying on LLM instructions.

    async def process_input(
            self,
            message: str, # User's CGM readings or initial interaction
            context: dict[str, Any] | None = None,
            db_manager: DatabaseManager | None = None # Kept for test compatibility
        ) -> str:
        """Process user input for CGM readings using the agent's SDK capabilities."""
        context = context or {}

        user_id = context.get('user_id')
        if not user_id or not isinstance(user_id, int):
            # For direct calls, this check is useful.
            raise ValueError("Authentication required. Please provide a valid user_id for CGMCollector.process_input.")

        # The agent's instructions and the 'insert_cgm_reading' tool will now handle
        # prompting, validation, retries, and confirmation.
        # The self.retry_count logic is removed from this direct invocation path.
        run_context = {"user_id": user_id}
        # If other parts of the incoming 'context' are relevant, add them to 'run_context'.

        try:
            agent_response = await self.run(
                message=message,
                context=run_context
            )
            return str(agent_response.final_output)
        except Exception as e:
            # Consider logging: import logging; logger = logging.getLogger(__name__); logger.error(f"Error: {e!s}")
            return f"Sorry, I encountered an issue while collecting CGM data: {e!s}"

    def _validate_readings_format(self, input_str: str) -> bool:
        """Validate the format of CGM readings input."""
        return bool(re.match(READING_PATTERN, input_str))

    async def _process_valid_readings(self, user_id: int, readings_input: str, db_manager: DatabaseManager | None = None) -> str:
        """Process and store valid CGM readings."""
        self.retry_count = 0  # Reset retry counter on success

        readings_values = [float(r.strip()) for r in readings_input.split(',')]

        success_count = 0
        error_messages = []
        detailed_results = [] # To store individual messages for clarity

        for reading_val in readings_values:
            result = await insert_cgm_reading(
                user_id=user_id,
                glucose_value=reading_val,
                db_manager=db_manager
            )
            detailed_results.append(result) # Store each result
            if "Successfully stored CGM reading" in result:
                success_count += 1
            else:
                # Extract the core error part if possible for summary
                error_summary = result.split(':', 1)[-1].strip() if ':' in result else result
                error_messages.append(f"- Reading {reading_val}: {error_summary}")

        response_parts = []
        if success_count > 0:
            response_parts.append(f"✅ Saved {success_count} out of {len(readings_values)} readings for user #{user_id}.")
        elif len(readings_values) > 0:
             response_parts.append(f"⚠️ Failed to save any of the {len(readings_values)} readings for user #{user_id}.")

        if error_messages:
            response_parts.append("Details:")
            response_parts.extend(error_messages)

        if not response_parts and len(readings_values) > 0:
             return "No readings were processed or results available."
        elif not readings_values:
            return "No readings provided to process."

        # Add next step prompt only if all were successful
        if success_count == len(readings_values) and success_count > 0:
             response_parts.append("Next, I can generate your meal plan—just let me know when you're ready.")

        return "\n".join(response_parts)


