"""
db_setup.py — Script to upgrade database schema for timetable project.
Run: python db_setup.py
"""
import mysql.connector
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import Config
from db import get_connection

def column_exists(cursor, table_name, column_name):
    query = """
        SELECT COLUMN_NAME 
        FROM INFORMATION_SCHEMA.COLUMNS 
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = %s
    """
    cursor.execute(query, (Config.DB_NAME, table_name, column_name))
    return cursor.fetchone() is not None

def run_migration():
    print("Connecting to the database...")
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. Modify users.role enum to include 'student'
    print("Updating users table role column...")
    try:
        cursor.execute("ALTER TABLE users MODIFY COLUMN role ENUM('admin', 'teacher', 'student') NOT NULL")
        conn.commit()
        print("[OK] Modified users.role enum.")
    except Exception as e:
        print(f"Error modifying users.role: {e}")

    # 2. Add columns to teachers table if they don't exist
    print("Updating teachers table columns...")
    teacher_cols = {
        "department": "VARCHAR(100) NULL",
        "cabin_no": "VARCHAR(50) NULL",
        "email": "VARCHAR(100) NULL",
        "phone": "VARCHAR(20) NULL",
        "status": "ENUM('pending', 'approved', 'rejected') DEFAULT 'approved'"
    }
    
    for col, definition in teacher_cols.items():
        if not column_exists(cursor, "teachers", col):
            try:
                cursor.execute(f"ALTER TABLE teachers ADD COLUMN {col} {definition}")
                conn.commit()
                print(f"[OK] Added column teachers.{col}")
            except Exception as e:
                print(f"Error adding teachers.{col}: {e}")
        else:
            print(f"[*] Column teachers.{col} already exists.")

    # 3. Create students table
    print("Creating students table...")
    create_students_sql = """
    CREATE TABLE IF NOT EXISTS students (
        student_id INT AUTO_INCREMENT PRIMARY KEY,
        uid INT UNIQUE,
        sname VARCHAR(100) NOT NULL,
        enrollment_no VARCHAR(50) UNIQUE NOT NULL,
        department VARCHAR(100),
        semester INT,
        email VARCHAR(100),
        phone VARCHAR(20),
        FOREIGN KEY (uid) REFERENCES users(uid) ON DELETE CASCADE
    )
    """
    try:
        cursor.execute(create_students_sql)
        conn.commit()
        print("[OK] Created students table.")
    except Exception as e:
        print(f"Error creating students table: {e}")

    # 4. Add student_id to users and link it to students table
    if not column_exists(cursor, "users", "student_id"):
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN student_id INT NULL")
            cursor.execute("ALTER TABLE users ADD FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE SET NULL")
            conn.commit()
            print("[OK] Added column users.student_id and linked foreign key.")
        except Exception as e:
            print(f"Error adding users.student_id: {e}")
    else:
        print("[*] Column users.student_id already exists.")

    # 5. Create appointments table
    print("Creating appointments table...")
    create_appointments_sql = """
    CREATE TABLE IF NOT EXISTS appointments (
        aid INT AUTO_INCREMENT PRIMARY KEY,
        student_id INT NOT NULL,
        tid INT NOT NULL,
        date DATE NOT NULL,
        start_time TIME NOT NULL,
        end_time TIME NOT NULL,
        status ENUM('pending', 'accepted', 'declined') DEFAULT 'pending',
        message TEXT,
        teacher_reply TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE CASCADE,
        FOREIGN KEY (tid) REFERENCES teachers(tid) ON DELETE CASCADE
    )
    """
    try:
        cursor.execute(create_appointments_sql)
        conn.commit()
        print("[OK] Created appointments table.")
    except Exception as e:
        print(f"Error creating appointments table: {e}")

    # 6. Create teacher_schedule table for overrides
    print("Creating teacher_schedule table...")
    create_schedule_sql = """
    CREATE TABLE IF NOT EXISTS teacher_schedule (
        id INT AUTO_INCREMENT PRIMARY KEY,
        tid INT NOT NULL,
        day VARCHAR(20) NULL,
        date DATE NULL,
        start_time TIME NOT NULL,
        end_time TIME NOT NULL,
        status ENUM('busy', 'available', 'on leave') NOT NULL,
        reason VARCHAR(255) NULL,
        FOREIGN KEY (tid) REFERENCES teachers(tid) ON DELETE CASCADE
    )
    """
    try:
        cursor.execute(create_schedule_sql)
        conn.commit()
        print("[OK] Created teacher_schedule table.")
    except Exception as e:
        print(f"Error creating teacher_schedule table: {e}")

    # 7. Upgrade default users and teachers data
    print("Ensuring existing data is correct...")
    try:
        cursor.execute("UPDATE teachers SET status = 'approved' WHERE status IS NULL")
        conn.commit()
        print("[OK] Updated null statuses in teachers table.")
    except Exception as e:
        print(f"Error updating teachers statuses: {e}")

    cursor.close()
    conn.close()
    print("Database migration complete.")


if __name__ == "__main__":
    run_migration()
