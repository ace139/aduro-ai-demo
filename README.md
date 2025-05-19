# Aduro AI Demo

A Python application that demonstrates AI agent capabilities with a user and CGM (Continuous Glucose Monitoring) data management system.

## Features

- **User Management**: Store and manage user information including personal details and health preferences
- **CGM Data Tracking**: Record and track continuous glucose monitoring readings
- **AI Integration**: Built with OpenAI's agent framework for intelligent interactions
- **CGM Collector Agent**: Specialized agent for collecting and validating CGM readings
- **Database**: SQLite database with proper schema and sample data generation

## Prerequisites

- Python 3.8+
- pip (Python package manager)
- OpenAI API key

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/aduro-ai-demo.git
   cd aduro-ai-demo
   ```

2. Create and activate a virtual environment (recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install the required dependencies using `uv`:
   ```bash
   uv pip install -r requirements.txt
   ```

4. (Optional) If you need to create a `uv.lock` file:
   ```bash
   uv pip compile requirements.txt -o requirements.lock
   ```

5. Set up your environment variables:
   - Copy `.env.example` to `.env`
   - Add your OpenAI API key:
     ```
     OPENAI_API_KEY=your_openai_api_key_here
     ```

## Database Setup

The application uses SQLite for data storage. To set up the database:

1. Run the database initialization script:
   ```bash
   python init_db.py
   ```

   This will:
   - Create a new SQLite database at `db/users.db`
   - Create the necessary tables (`users` and `cgm_readings`)
   - Generate sample data (100 users with 30 days of CGM readings each)

## Database Schema

### Users Table
- `id`: Primary key
- `first_name`: User's first name
- `last_name`: User's last name
- `city`: User's city
- `email`: User's email (unique)
- `date_of_birth`: User's date of birth
- `dietary_preference`: Dietary preference (vegetarian/non-vegetarian/vegan)
- `medical_conditions`: Comma-separated list of medical conditions
- `physical_limitations`: Comma-separated list of physical limitations
- `created_at`: Timestamp of record creation

### CGM Readings Table
- `id`: Primary key
- `user_id`: Foreign key to users table
- `reading`: CGM reading value (mg/dL)
- `reading_type`: Type of reading (breakfast/lunch/dinner)
- `timestamp`: When the reading was taken

## Running the Application

To start the AI agent demo:

```bash
python main.py
```

To run the CGM Collector agent directly:

```bash
python agents/cgm_collector.py
```

This will execute the test suite for the CGM Collector agent.

## CGM Collector Agent

The CGM Collector is an AI agent designed to collect and validate Continuous Glucose Monitoring (CGM) readings from users. It provides a conversational interface for users to input their glucose readings and handles data validation and storage.

### Key Features

- Validates input format for CGM readings
- Supports multiple readings in a single input (comma-separated)
- Implements retry mechanism for invalid inputs
- Requires user authentication via user_id
- Provides clear, user-friendly error messages

### Usage

```python
from agents.cgm_collector import CGMCollector
import asyncio

async def main():
    # Initialize the agent
    agent = CGMCollector()
    
    # Process input with user context
    response = await agent.process_input("95,110,102", {"user_id": 123})
    print(response)

if __name__ == "__main__":
    asyncio.run(main())
```

### Input Format

- Single reading: `95`
- Multiple readings: `95,110,102,89`
- Readings with spaces: `95, 110, 102` (spaces are automatically handled)

### Error Handling

The agent will provide helpful error messages for:
- Missing or invalid user authentication
- Incorrect input format
- Maximum retry attempts reached

## Project Structure

```
.
├── .env.example           # Example environment variables
├── .gitignore             # Git ignore file
├── README.md              # This file
├── init_db.py             # Database initialization script
├── main.py                # Main application entry point
├── agents/                # Agent-related code
│   ├── __init__.py
│   └── cgm_collector.py   # CGM Collector agent implementation
├── db/                    # Database directory (auto-created)
│   └── users.db          # SQLite database file
└── requirements.txt       # Python dependencies
```

## Development

### Adding New Features

1. Create a new branch for your feature:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. Make your changes and commit them:
   ```bash
   git add .
   git commit -m "Add your feature description"
   ```

3. Push to the branch:
   ```bash
   git push origin feature/your-feature-name
   ```

4. Create a pull request on GitHub

### Running Tests

```bash
# Run all tests
pytest

# Run tests with coverage report
pytest --cov=.
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Built with Python and SQLite
- Uses OpenAI's agent framework
- Sample data generated using Faker