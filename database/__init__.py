from .database import Database

# Initialize the database instance
db = Database()

# Expose the functions directly for backwards compatibility
is_approved = db.is_approved
update_violations = db.update_violations
add_approved_user = db.add_approved_user
remove_approved_user = db.remove_approved_user
get_user_violations = db.get_user_violations
get_all_users = db.get_all_approved_users

__all__ = [
    'Database',
    'db',
    'is_approved',
    'update_violations',
    'add_approved_user',
    'remove_approved_user',
    'get_user_violations',
    'get_all_users'
]