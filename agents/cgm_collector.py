"""
CGM-Collector Agent for collecting and storing CGM readings.
"""

import re
import unittest
from datetime import datetime
from typing import Dict, Any, Optional
from unittest.mock import AsyncMock

from agents import Agent, function_tool

# Constants
MAX_RETRIES = 2
READING_PATTERN = r'^\d{1,3}(\s*,\s*\d{1,3})*$'

@function_tool
async def insert_cgm_reading(
    user_id: int,
    reading: float,
    reading_type: str = "fingerstick",
    timestamp: Optional[datetime] = None
) -> str:
    """
    Inserts one CGM reading into the cgm_readings table.
    """
    ts = timestamp or datetime.now()
    return f"Successfully stored reading of {reading} mg/dL for user #{user_id} at {ts}"

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
        
        # Parse readings
        readings = [float(r.strip()) for r in readings_input.split(',')]
        
        # Store each reading
        for reading in readings:
            await insert_cgm_reading(
                user_id=user_id,
                reading=reading,
                reading_type="fingerstick",
                timestamp=datetime.now()
            )
        
        return f"✅ Saved {len(readings)} readings for user #{user_id}. Next, I can generate your meal plan—just let me know when you're ready."


# Tests

class TestCGMCollector(unittest.IsolatedAsyncioTestCase):
    """Unit tests for CGMCollector agent."""
    
    async def asyncSetUp(self):
        """Set up test fixtures."""
        self.agent = CGMCollector()
        self.agent.insert_cgm_reading = AsyncMock(return_value="Mocked DB response")
    
    async def test_valid_readings(self):
        """Test with valid readings input."""
        context = {"user_id": 123}
        
        # Initial prompt
        response = await self.agent.process_input("hi", context)
        self.assertIn("Please enter your latest CGM readings", response)
        
        # Process valid readings
        response = await self.agent.process_input("95, 110, 102", context)
        self.assertIn("✅ Saved 3 readings for user #123", response)
        self.assertEqual(self.agent.insert_cgm_reading.await_count, 3)
    
    async def test_invalid_readings_retry(self):
        """Test retry mechanism with invalid inputs."""
        context = {"user_id": 123}
        
        # Initial prompt
        await self.agent.process_input("hi", context)
        
        # First invalid input
        response = await self.agent.process_input("95;110;102", context)
        self.assertEqual(response, "I didn't understand. Send readings like `95,110,102`.")
        
        # Second invalid input
        response = await self.agent.process_input("abc", context)
        self.assertEqual(response, "I didn't understand. Send readings like `95,110,102`.")
        
        # Third invalid input should fail
        response = await self.agent.process_input("123;456", context)
        self.assertEqual(response, "Maximum retry attempts reached. Please try again later.")
    
    async def test_missing_user_id(self):
        """Test authentication error when user_id is missing."""
        with self.assertRaises(ValueError) as context:
            await self.agent.process_input("hi", {})
        self.assertIn("Authentication required", str(context.exception))


if __name__ == "__main__":
    # Run tests
    unittest.main(argv=['first-arg-is-ignored'], exit=False)
    
    # Example usage
    def show_usage_example():
        """Show example usage of the CGMCollector agent."""
        print("Example usage of CGMCollector:")
        print("1. Create an agent: agent = CGMCollector()")
        print('2. Process input with user context: await agent.process_input("95,110,102", {"user_id": 123})')
    
    show_usage_example()
