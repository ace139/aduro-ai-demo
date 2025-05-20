import random
import sqlite3
from pathlib import Path

from faker import Faker

# Initialize Faker
fake = Faker()

# Database directory and file path
DB_DIR = Path('db')
DB_PATH = DB_DIR / 'users.db'

def create_connection():
    """Create a database connection to the SQLite database."""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        return conn
    except sqlite3.Error as e:
        print(f"Error connecting to database: {e}")
    return conn

def create_tables(conn):
    """Create the database tables."""
    sql_create_users_table = """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        first_name TEXT NOT NULL,
        last_name TEXT NOT NULL,
        city TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        date_of_birth DATE NOT NULL,
        dietary_preference TEXT CHECK(dietary_preference IN ('vegetarian', 'non-vegetarian', 'vegan')),
        medical_conditions TEXT,
        physical_limitations TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """

    sql_create_cgm_readings_table = """
    CREATE TABLE IF NOT EXISTS cgm_readings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        reading REAL NOT NULL,
        reading_type TEXT NOT NULL,
        timestamp DATETIME NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    )
    """

    try:
        c = conn.cursor()
        c.execute(sql_create_users_table)
        c.execute('DROP TABLE IF EXISTS cgm_readings')
        c.execute(sql_create_cgm_readings_table)
        conn.commit()
    except sqlite3.Error as e:
        print(f"Error creating tables: {e}")
        conn.rollback()

def generate_sample_data(count=100):
    """Generate sample user data."""
    users = []

    dietary_prefs = ['vegetarian', 'non-vegetarian', 'vegan']
    medical_conditions = [
        'None',
        'Type 2 diabetes',
        'Hypertension',
        'High cholesterol',
        'Heart disease',
        'Asthma',
        'Arthritis'
    ]

    physical_limitations = [
        'None',
        'Mobility issues',
        'Visual impairment',
        'Hearing impairment',
        'Limited dexterity'
    ]

    for _ in range(count):
        first_name = fake.first_name()
        last_name = fake.last_name()
        email = f"{first_name.lower()}.{last_name.lower()}@example.com"

        user = (
            first_name,
            last_name,
            fake.city(),
            email,
            fake.date_of_birth(minimum_age=18, maximum_age=90).strftime('%Y-%m-%d'),
            random.choice(dietary_prefs),
            ', '.join(random.sample(medical_conditions, random.randint(0, 2))).replace('None, ', '').replace(', None', '') or 'None',
            ', '.join(random.sample(physical_limitations, random.randint(0, 2))).replace('None, ', '').replace(', None', '') or 'None'
        )
        users.append(user)

    return users

def insert_sample_data(conn, users):
    """Insert sample data into the users table and return the user IDs."""
    sql = """
    INSERT INTO users
    (first_name, last_name, city, email, date_of_birth, dietary_preference, medical_conditions, physical_limitations)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """

    try:
        c = conn.cursor()
        c.executemany(sql, users)
        conn.commit()
        print(f"Successfully inserted {c.rowcount} records into the users table.")

        # Return the list of user IDs that were just inserted
        c.execute("SELECT id FROM users ORDER BY id DESC LIMIT ?", (len(users),))
        return [row[0] for row in c.fetchall()]
    except sqlite3.Error as e:
        print(f"Error inserting data: {e}")
        conn.rollback()
        return []

def generate_cgm_readings(user_ids, days_back=30):
    """Generate sample CGM readings for each user."""
    import random
    from datetime import datetime, timedelta

    readings = []
    reading_types = ['breakfast', 'lunch', 'dinner']

    for user_id in user_ids:
        # Generate readings for the last N days
        for day in range(days_back):
            date = datetime.now() - timedelta(days=day)

            # Generate 3 readings per day (breakfast, lunch, dinner)
            for i, reading_type in enumerate(reading_types):
                # Generate a reading time around typical meal times
                hour = 8 + (i * 5)  # 8am, 1pm, 6pm
                reading_time = date.replace(hour=hour, minute=random.randint(0, 59))

                # Generate a random reading between 70-180 mg/dL (typical CGM range)
                # Add some variation based on meal type
                base_reading = random.uniform(80, 160)
                if reading_type == 'breakfast':
                    reading = base_reading + random.uniform(0, 20)  # Higher after breakfast
                elif reading_type == 'lunch':
                    reading = base_reading + random.uniform(-10, 10)  # More stable
                else:  # dinner
                    reading = base_reading + random.uniform(-20, 0)  # Lower in the evening

                # Ensure reading is within reasonable bounds
                reading = max(70, min(200, reading))

                readings.append((
                    user_id,
                    round(reading, 1),
                    reading_type,
                    reading_time.strftime('%Y-%m-%d %H:%M:%S')
                ))

    return readings

def insert_cgm_readings(conn, readings):
    """Insert CGM readings into the database."""
    sql = """
    INSERT INTO cgm_readings (user_id, reading, reading_type, timestamp)
    VALUES (?, ?, ?, ?)
    """

    try:
        c = conn.cursor()
        c.executemany(sql, readings)
        conn.commit()
        print(f"Successfully inserted {c.rowcount} CGM readings.")
    except sqlite3.Error as e:
        print(f"Error inserting CGM readings: {e}")
        conn.rollback()

def main():
    # Create db directory if it doesn't exist
    DB_DIR.mkdir(exist_ok=True)

    # Delete existing database if it exists
    if DB_PATH.exists():
        print(f"Deleting existing database at {DB_PATH}")
        DB_PATH.unlink()

    # Create a database connection
    conn = create_connection()
    if conn is not None:
        try:
            # Enable foreign key constraints
            conn.execute("PRAGMA foreign_keys = ON")

            # Create tables
            print("Creating database tables...")
            create_tables(conn)

            # Generate and insert sample user data
            print("Generating sample user data...")
            users = generate_sample_data(100)
            user_ids = insert_sample_data(conn, users)

            if user_ids:
                # Generate and insert sample CGM readings
                print(f"Generating CGM readings for {len(user_ids)} users...")
                cgm_readings = generate_cgm_readings(user_ids, days_back=30)  # 30 days of data
                insert_cgm_readings(conn, cgm_readings)

            print(f"\nDatabase created successfully at {DB_PATH}")
            print(f"- Users: {len(users)}")
            if user_ids:
                print(f"- CGM readings: {len(cgm_readings)} (approx. {len(cgm_readings)//len(user_ids)} per user)")

        except Exception as e:
            print(f"An error occurred: {e}")
            if conn:
                conn.rollback()
        finally:
            # Close the connection
            if conn:
                conn.close()
    else:
        print("Error! Cannot create the database connection.")

if __name__ == "__main__":
    print("This script will create a SQLite database with sample user data.")
    print("The database will be created at:", str(DB_PATH.resolve()))
    print("\nThe script will:")
    print("1. Create a new SQLite database file (deleting existing if present)")
    print("2. Create 'users' and 'cgm_readings' tables with appropriate schemas")
    print("3. Generate 100 sample user records")
    print("4. Generate 30 days of CGM readings (3 readings per day) for each user")
    print("5. Insert all records into the database")
    print("\nTo proceed with database creation, please uncomment the 'main()' call at the bottom of this file.")
    print("Then run the script with: python init_db.py")

    # Uncomment the line below to run the database initialization
    # main()
