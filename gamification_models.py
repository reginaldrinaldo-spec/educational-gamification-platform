from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Badge(db.Model):
    __tablename__ = "badges"
    
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String, unique=True, nullable=False)
    name = db.Column(db.String, nullable=False)
    description = db.Column(db.String)
    icon_url = db.Column(db.String)
    criteria = db.Column(db.JSON)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Achievement(db.Model):
    __tablename__ = "achievements"
    
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String, unique=True, nullable=False)
    name = db.Column(db.String, nullable=False)
    description = db.Column(db.String)
    icon_url = db.Column(db.String)
    criteria = db.Column(db.JSON)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class UserBadge(db.Model):
    __tablename__ = "user_badges"
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    badge_id = db.Column(db.Integer, db.ForeignKey("badges.id", ondelete="CASCADE"), nullable=False)
    awarded_at = db.Column(db.DateTime, default=datetime.utcnow)
    source = db.Column(db.String)
    related_quiz_id = db.Column(db.Integer, db.ForeignKey("quizzes.id"))
    
    badge = db.relationship("Badge")
    __table_args__ = (db.UniqueConstraint("user_id", "badge_id", name="uq_user_badge"),)

class UserAchievement(db.Model):
    __tablename__ = "user_achievements"
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    achievement_id = db.Column(db.Integer, db.ForeignKey("achievements.id", ondelete="CASCADE"), nullable=False)
    unlocked_at = db.Column(db.DateTime, default=datetime.utcnow)
    progress_value = db.Column(db.Integer)
    source = db.Column(db.String)
    
    achievement = db.relationship("Achievement")
    __table_args__ = (db.UniqueConstraint("user_id", "achievement_id", name="uq_user_achievement"),)

class XPTransaction(db.Model):
    __tablename__ = "xp_transactions"
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    amount = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String, nullable=False)
    source = db.Column(db.String)
    category_code = db.Column(db.String)
    related_quiz_id = db.Column(db.Integer, db.ForeignKey("quizzes.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class LeaderboardEntry(db.Model):
    __tablename__ = "leaderboard_entries"
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    period_type = db.Column(db.String, nullable=False)
    period_start = db.Column(db.Date)
    period_end = db.Column(db.Date)
    category_code = db.Column(db.String)
    rank = db.Column(db.Integer, nullable=False)
    total_xp = db.Column(db.Integer, nullable=False)
    snapshot_at = db.Column(db.DateTime, default=datetime.utcnow)

# XP & Level Helper Functions
MAX_LEVEL = 50
XP_PER_LEVEL = 100

def get_user_total_xp(user_id: int) -> int:
    from sqlalchemy import func
    total = (
        db.session.query(func.coalesce(func.sum(XPTransaction.amount), 0))
        .filter(XPTransaction.user_id == user_id)
        .scalar()
    )
    return int(total or 0)

def xp_to_level(total_xp: int) -> int:
    level = (total_xp // XP_PER_LEVEL) + 1
    return min(level, MAX_LEVEL)

def get_level_progress(total_xp: int) -> dict:
    level = xp_to_level(total_xp)
    xp_for_current_level = (level - 1) * XP_PER_LEVEL
    xp_into_level = total_xp - xp_for_current_level
    xp_to_next = XP_PER_LEVEL
    progress_pct = min(100, max(0, int((xp_into_level / xp_to_next) * 100)))
    
    return {
        "level": level,
        "current_xp": total_xp,
        "xp_into_level": xp_into_level,
        "xp_to_next_level": xp_to_next,
        "progress_pct": progress_pct,
    }

def award_xp(
    user_id: int,
    amount: int,
    reason: str,
    source: str = None,
    category_code: str = None,
    related_quiz_id: int = None
) -> dict:
    tx = XPTransaction(
        user_id=user_id,
        amount=amount,
        reason=reason,
        source=source,
        category_code=category_code,
        related_quiz_id=related_quiz_id,
    )
    db.session.add(tx)
    db.session.flush()
    
    total_xp = get_user_total_xp(user_id)
    level_info = get_level_progress(total_xp)
    
    return {
        "transaction_id": tx.id,
        "total_xp": total_xp,
        **level_info,
    }
