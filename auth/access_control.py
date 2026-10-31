# auth/access_control.py

class AccessControl:

    @staticmethod
    def is_verified(user):

        return user.verified

    @staticmethod
    def is_admin(user):

        return user.role.lower() == "admin"

    @staticmethod
    def is_owner(user):

        return user.role.lower() == "owner"

    @staticmethod
    def is_premium(user):

        return user.role.lower() in (
            "premium",
            "admin",
            "owner"
        )