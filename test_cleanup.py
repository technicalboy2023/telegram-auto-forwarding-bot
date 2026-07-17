import logging
from database.db import Database
from utils.cleanup import CleanupScheduler

def main():
    # Setup simple terminal logging so we can see what it does
    logging.basicConfig(
        level=logging.INFO, 
        format="%(asctime)s │ %(levelname)s │ %(message)s"
    )
    
    print("==================================================")
    print("🧹 STARTING MANUAL CLEANUP TEST")
    print("==================================================")
    
    # Initialize Database (It will safely connect to bot_data.db)
    db = Database()
    
    # Initialize Scheduler
    scheduler = CleanupScheduler(db)
    
    # Force run the cleanup synchronously
    report = scheduler.run_full_cleanup()
    
    print("==================================================")
    print("✅ CLEANUP FINISHED!")
    print(f"📊 SUMMARY: {report.summary()}")
    print("==================================================")
    
    db.close()

if __name__ == "__main__":
    main()
