"""
CGM-Collector Agent for collecting and storing CGM readings.
"""

import re
import sqlite3
from pathlib import Path
from datetime import datetime, time
from typing import Dict, Any, Optional

from agents import Agent, function_tool

# Constants
MAX_RETRIES = 2
READING_PATTERN = r'^\d{1,3}(\s*,\s*\d{1,3})*$'
DB_PATH = Path(__file__).resolve().parent.parent / "db" / "users.db"

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
    reading: float,
    timestamp: Optional[datetime] = None
) -> str:
    """
    Inserts one CGM reading into the cgm_readings table in the SQLite database.
    The reading_type is automatically inferred from the timestamp.
    
    Args:
        user_id: The ID of the user
        reading: The blood glucose reading in mg/dL
        timestamp: When the reading was taken (defaults to now)
        
    Returns:
        str: Status message indicating success or failure
    """
    ts = timestamp or datetime.now()
    reading_type = _infer_reading_type(ts)
    conn = None
    try:
        if not DB_PATH.exists():
            return f"Error: Database file not found at {DB_PATH}. Please ensure it has been initialized."
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute(
            "INSERT INTO cgm_readings (user_id, reading, reading_type, timestamp) VALUES (?, ?, ?, ?)",
            (user_id, reading, reading_type, ts.strftime('%Y-%m-%d %H:%M:%S'))
        )
        conn.commit()
        return f"Successfully stored reading {reading} mg/dL for user #{user_id} at {ts.strftime('%Y-%m-%d %H:%M:%S')}."
    except sqlite3.IntegrityError as e:
        if conn:
            conn.rollback()
        if "FOREIGN KEY constraint failed" in str(e):
             return f"Error: User ID #{user_id} not found in the database. Cannot store reading."
        return f"Error storing reading for user #{user_id}: Database integrity error ({e})."
    except sqlite3.Error as e:
        if conn:
            conn.rollback()
        return f"Error storing reading {reading} mg/dL for user #{user_id}: A database error occurred ({e})."
    finally:
        if conn:
            conn.close()

class CGMCollector(Agent):
    """Agent for collecting and storing CGM readings."""
    
    def __init__(self):
        instructions = """
        You are a clinical CGM data ingestion assistant. Your goal is to collect valid 
        blood-glucose readings from the user, validate formats, and store them in the 
        database via the provided tool. Be concise and professional in your responses.
        """
        super().__init__(
            name="cgm_collector",
            instructions=instructions,
            tools=[insert_cgm_reading]
        )
        self.retry_count = 0

    async def process_input(
        self, 
        message: str, 
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Process user input and handle the CGM reading collection flow."""
        context = context or {}
        
        # Validate user_id
        user_id = context.get('user_id')
        if not user_id or not isinstance(user_id, int):
            raise ValueError("Authentication required. Please provide a valid user_id.")
        
        # Check if we're in retry mode
        if self.retry_count > 0:
            if self._validate_readings_format(message):
                return await self._process_valid_readings(user_id, message)
            else:
                self.retry_count += 1
                if self.retry_count > MAX_RETRIES:
                    self.retry_count = 0
                    return "Maximum retry attempts reached. Please try again later."
                return "I didn't understand. Send readings like `95,110,102`."
        
        # Initial prompt for readings
        if not message or message.strip().lower() in ['hi', 'hello', 'start']:
            return "Please enter your latest CGM readings in mg/dL as a comma-separated list (e.g. `95,110,102`)."
        
        # Process the readings if provided
        if self._validate_readings_format(message):
            return await self._process_valid_readings(user_id, message)
        else:
            self.retry_count = 1
            return "I didn't understand. Send readings like `95,110,102`."
    
    def _validate_readings_format(self, input_str: str) -> bool:
        """Validate the format of CGM readings input."""
        return bool(re.match(READING_PATTERN, input_str))
    
    async def _process_valid_readings(self, user_id: int, readings_input: str) -> str:
        """Process and store valid CGM readings."""
        self.retry_count = 0  # Reset retry counter on success
        
        readings_values = [float(r.strip()) for r in readings_input.split(',')]
        
        success_count = 0
        error_messages = []
        detailed_results = [] # To store individual messages for clarity
        
        for reading_val in readings_values:
            result_message = await insert_cgm_reading(
                user_id=user_id,
                reading=reading_val,
                timestamp=datetime.now()
            )
            detailed_results.append(result_message) # Store each result
            if "Successfully stored" in result_message:
                success_count += 1
            else:
                # Extract the core error part if possible for summary
                error_summary = result_message.split(':', 1)[-1].strip() if ':' in result_message else result_message
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


