import unittest
from unittest.mock import AsyncMock, patch, ANY
from aduro_agents.cgm_collector import CGMCollector

class TestCGMCollector(unittest.IsolatedAsyncioTestCase):
    """Unit tests for CGMCollector agent logic, mocking the database interaction."""

    def setUp(self):
        """Set up test fixtures for each test."""
        # Instantiate agent here if it's lightweight and doesn't need async setup for itself
        self.agent = CGMCollector()

    @patch('aduro_agents.cgm_collector.insert_cgm_reading', new_callable=AsyncMock)
    async def test_valid_readings_flow(self, mock_insert_cgm_reading):
        """Test with valid readings input, ensuring the tool is called."""
        # Configure mock to simulate successful database insertions for all calls
        mock_insert_cgm_reading.return_value = "Successfully stored reading 0 mg/dL for user #0 at 2023-01-01 00:00:00."

        context = {"user_id": 123}
        
        # Initial prompt
        response = await self.agent.process_input("hi", context)
        self.assertIn("Please enter your latest CGM readings", response)
        
        # Process valid readings
        response = await self.agent.process_input("95, 110, 102", context)

        self.assertIn("✅ Saved 3 out of 3 readings for user #123.", response)
        self.assertIn("Next, I can generate your meal plan—just let me know when you're ready.", response)
        
        self.assertEqual(mock_insert_cgm_reading.await_count, 3)
        mock_insert_cgm_reading.assert_any_await(user_id=123, reading=95.0, reading_type="fingerstick", timestamp=ANY)
        mock_insert_cgm_reading.assert_any_await(user_id=123, reading=110.0, reading_type="fingerstick", timestamp=ANY)
        mock_insert_cgm_reading.assert_any_await(user_id=123, reading=102.0, reading_type="fingerstick", timestamp=ANY)

    @patch('aduro_agents.cgm_collector.insert_cgm_reading', new_callable=AsyncMock)
    async def test_invalid_readings_retry_flow(self, mock_insert_cgm_reading):
        """Test retry mechanism with invalid inputs."""
        context = {"user_id": 123}
        self.agent.retry_count = 0 # Ensure retry count is reset before test
        
        # Initial prompt (optional, depends on how process_input handles state)
        # await self.agent.process_input("hi", context) 
        
        # First invalid input
        response = await self.agent.process_input("95;110;102", context)
        self.assertEqual(response, "I didn't understand. Send readings like `95,110,102`.")
        self.assertEqual(self.agent.retry_count, 1)
        
        # Second invalid input
        response = await self.agent.process_input("abc", context)
        self.assertEqual(response, "I didn't understand. Send readings like `95,110,102`.")
        self.assertEqual(self.agent.retry_count, 2)
        
        # Third invalid input (MAX_RETRIES is 2, so this attempt triggers max_retries)
        response = await self.agent.process_input("123;456", context)
        self.assertEqual(response, "Maximum retry attempts reached. Please try again later.")
        self.assertEqual(self.agent.retry_count, 0) # Retry count should reset

        mock_insert_cgm_reading.assert_not_awaited()

    async def test_missing_user_id_error(self):
        """Test authentication error when user_id is missing."""
        with self.assertRaises(ValueError) as err_context:
            await self.agent.process_input("hi", {})
        self.assertIn("Authentication required. Please provide a valid user_id.", str(err_context.exception))

    @patch('aduro_agents.cgm_collector.insert_cgm_reading', new_callable=AsyncMock)
    async def test_partial_db_failure(self, mock_insert_cgm_reading):
        """Test flow when some readings save successfully and others fail."""
        mock_insert_cgm_reading.side_effect = [
            "Successfully stored reading 100.0 mg/dL for user #789 at ...",
            "Error: User ID #789 not found in the database. Cannot store reading.",
            "Successfully stored reading 120.0 mg/dL for user #789 at ..."
        ]
        
        context = {"user_id": 789}
        response = await self.agent.process_input("100, 150, 120", context)
        
        self.assertIn("✅ Saved 2 out of 3 readings for user #789.", response)
        self.assertIn("Details:", response)
        self.assertIn("- Reading 150.0: User ID #789 not found in the database. Cannot store reading.", response)
        
        self.assertEqual(mock_insert_cgm_reading.await_count, 3)

    @patch('aduro_agents.cgm_collector.insert_cgm_reading', new_callable=AsyncMock)
    async def test_all_db_failure(self, mock_insert_cgm_reading):
        """Test flow when all readings fail to save to the database."""
        mock_insert_cgm_reading.side_effect = [
            "Error: Database file not found at ...",
            "Error: A database error occurred (...)."
        ]
        
        context = {"user_id": 456}
        response = await self.agent.process_input("80, 85", context)
        
        self.assertIn("⚠️ Failed to save any of the 2 readings for user #456.", response)
        self.assertIn("Details:", response)
        self.assertIn("- Reading 80.0: Database file not found at ...", response)
        self.assertIn("- Reading 85.0: A database error occurred (...).", response)
        self.assertNotIn("Next, I can generate your meal plan", response)
        
        self.assertEqual(mock_insert_cgm_reading.await_count, 2)

if __name__ == "__main__":
    unittest.main()
