from flask import Blueprint, request, jsonify
from sqlalchemy import func, desc
import logging
from datetime import datetime, timedelta
from gamification_models import (
    db, Badge, Achievement, UserBadge, UserAchievement,
    XPTransaction, LeaderboardEntry,
    get_user_total_xp, get_level_progress, award_xp,
    update_streak, update_category_progress, check_streak_badges, check_category_mastery_badge
)

gamification_bp = Blueprint("gamification", __name__, url_prefix="/api")

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

def get_user_id_from_request():
    user_id = request.headers.get("X-User-Id") or request.args.get("user_id")
    if not user_id:
        raise ValueError("Missing user_id")
    return int(user_id)

@gamification_bp.route("/badges", methods=["GET"])
def get_badges():
    badges = Badge.query.filter_by(is_active=True).all()
    return jsonify([
        {
            "id": b.id,
            "code": b.code,
            "name": b.name,
            "description": b.description,
            "iconUrl": b.icon_url,
        }
        for b in badges
    ])

@gamification_bp.route("/badges", methods=["POST"])
def award_badge():
    data = request.get_json() or {}
    user_id = data.get("user_id")
    badge_code = data.get("badge_code")
    source = data.get("source")
    related_quiz_id = data.get("related_quiz_id")
    
    if not user_id or not badge_code:
        return jsonify({"error": "user_id and badge_code are required"}), 400
    
    badge = Badge.query.filter_by(code=badge_code, is_active=True).first()
    if not badge:
        return jsonify({"error": "Badge not found"}), 404
    
    existing = UserBadge.query.filter_by(user_id=user_id, badge_id=badge.id).first()
    if existing:
        return jsonify({"message": "Badge already awarded"}), 200
    
    user_badge = UserBadge(
        user_id=user_id,
        badge_id=badge.id,
        source=source,
        related_quiz_id=related_quiz_id,
    )
    db.session.add(user_badge)
    db.session.commit()
    
    return jsonify({
        "message": "Badge awarded",
        "user_badge": {
            "id": user_badge.id,
            "user_id": user_badge.user_id,
            "badge_id": user_badge.badge_id,
            "awarded_at": user_badge.awarded_at.isoformat(),
        },
    }), 201

@gamification_bp.route("/achievements", methods=["GET"])
def get_achievements():
    achievements = Achievement.query.filter_by(is_active=True).all()
    return jsonify([
        {
            "id": a.id,
            "code": a.code,
            "name": a.name,
            "description": a.description,
            "iconUrl": a.icon_url,
        }
        for a in achievements
    ])

@gamification_bp.route("/achievements", methods=["POST"])
def unlock_achievement():
    data = request.get_json() or {}
    user_id = data.get("user_id")
    achievement_code = data.get("achievement_code")
    source = data.get("source")
    progress_value = data.get("progress_value")
    
    if not user_id or not achievement_code:
        return jsonify({"error": "user_id and achievement_code are required"}), 400
    
    achievement = Achievement.query.filter_by(code=achievement_code, is_active=True).first()
    if not achievement:
        return jsonify({"error": "Achievement not found"}), 404
    
    existing = UserAchievement.query.filter_by(
        user_id=user_id,
        achievement_id=achievement.id
    ).first()
    if existing:
        return jsonify({"message": "Achievement already unlocked"}), 200
    
    ua = UserAchievement(
        user_id=user_id,
        achievement_id=achievement.id,
        source=source,
        progress_value=progress_value,
    )
    db.session.add(ua)
    db.session.commit()
    
    return jsonify({
        "message": "Achievement unlocked",
        "user_achievement": {
            "id": ua.id,
            "user_id": ua.user_id,
            "achievement_id": ua.achievement_id,
            "unlocked_at": ua.unlocked_at.isoformat(),
        },
    }), 201

@gamification_bp.route("/xp/award", methods=["POST"])
def api_award_xp():
    data = request.get_json() or {}
    user_id = data.get("user_id")
    amount = data.get("amount")
    reason = data.get("reason")
    source = data.get("source")
    category_code = data.get("category_code")
    related_quiz_id = data.get("related_quiz_id")
    
    if not user_id or amount is None or not reason:
        return jsonify({"error": "user_id, amount and reason are required"}), 400
    
    try:
        amount = int(amount)
    except ValueError:
        return jsonify({"error": "amount must be an integer"}), 400
    
    result = award_xp(
        user_id=user_id,
        amount=amount,
        reason=reason,
        source=source,
        category_code=category_code,
        related_quiz_id=related_quiz_id,
    )
    db.session.commit()
    
    return jsonify({
        "message": "XP awarded",
        "result": result,
    }), 201

@gamification_bp.route("/user/profile", methods=["GET"])
def get_user_profile():
    user_id = request.args.get("user_id")
    if not user_id:
        return jsonify({"error": "user_id is required"}), 400
    
    user_id = int(user_id)
    total_xp = get_user_total_xp(user_id)
    level_info = get_level_progress(total_xp)
    
    user_badges = UserBadge.query.filter_by(user_id=user_id).join(Badge).all()
    badges = [
        {
            "id": ub.badge.id,
            "code": ub.badge.code,
            "name": ub.badge.name,
            "iconUrl": ub.badge.icon_url,
            "awarded_at": ub.awarded_at.isoformat(),
        }
        for ub in user_badges
    ]
    
    user_achievements = UserAchievement.query.filter_by(user_id=user_id).join(Achievement).all()
    achievements = [
        {
            "id": ua.achievement.id,
            "code": ua.achievement.code,
            "name": ua.achievement.name,
            "iconUrl": ua.achievement.icon_url,
            "unlocked_at": ua.unlocked_at.isoformat(),
        }
        for ua in user_achievements
    ]
    
    quizzes_completed = (
        db.session.query(func.count(func.distinct(XPTransaction.related_quiz_id)))
        .filter(
            XPTransaction.user_id == user_id,
            XPTransaction.reason == "quiz_completed",
            XPTransaction.related_quiz_id.isnot(None),
        )
        .scalar()
    )
    
    return jsonify({
        "user_id": user_id,
        "xp": level_info["current_xp"],
        "level": level_info["level"],
        "progress_pct": level_info["progress_pct"],
        "xp_into_level": level_info["xp_into_level"],
        "xp_to_next_level": level_info["xp_to_next_level"],
        "quizzes_completed": quizzes_completed or 0,
        "badges": badges,
        "achievements": achievements,
    })

@gamification_bp.route("/leaderboard", methods=["GET"])
def get_leaderboard():
    period = request.args.get("period", "global")
    category_code = request.args.get("category_code")
    try:
        limit = int(request.args.get("limit", 20))
    except ValueError:
        limit = 20
    
    tx_query = db.session.query(
        XPTransaction.user_id.label("user_id"),
        func.coalesce(func.sum(XPTransaction.amount), 0).label("total_xp"),
    )
    
    if category_code:
        tx_query = tx_query.filter(XPTransaction.category_code == category_code)
    
    if period == "weekly":
        one_week_ago = datetime.utcnow() - timedelta(days=7)
        tx_query = tx_query.filter(XPTransaction.created_at >= one_week_ago)
    
    tx_query = tx_query.group_by(XPTransaction.user_id).order_by(desc("total_xp")).limit(limit)
    rows = tx_query.all()
    
    leaderboard = []
    rank = 1
    for row in rows:
        leaderboard.append({
            "rank": rank,
            "user_id": row.user_id,
            "total_xp": int(row.total_xp or 0),
        })
        rank += 1
    
    return jsonify({
        "period": period,
        "category_code": category_code,
        "results": leaderboard,
    })

# ----- QUIZ COMPLETION WITH FULL GAMIFICATION -----
@gamification_bp.route("/quizzes/complete", methods=["POST"])
def complete_quiz():
    """
    Complete a quiz and award XP, badges, and track progress.
    Payload: {
        user_id, quiz_id, score, total_questions,
        time_taken_seconds, category
    }
    """
    data = request.get_json() or {}
    user_id = data.get("user_id")
    quiz_id = data.get("quiz_id")
    score = data.get("score")
    total_questions = data.get("total_questions")
    time_taken_seconds = data.get("time_taken_seconds")
    category = data.get("category", "general")
    
    if not all([user_id, quiz_id is not None, score is not None, total_questions, time_taken_seconds]):
        return jsonify({"error": "Missing required fields"}), 400
    
    try:
        user_id = int(user_id)
        score = int(score)
        total_questions = int(total_questions)
        time_taken_seconds = int(time_taken_seconds)
    except ValueError:
        return jsonify({"error": "Invalid numeric values"}), 400
    
    percentage = (score / total_questions) * 100.0 if total_questions > 0 else 0
    
    # Calculate XP: 10 per correct + bonuses
    base_xp = score * 10
    bonus_xp = 0
    
    # Perfect score bonus
    if percentage == 100.0:
        bonus_xp += 20
    
    # Speed bonus (< 30 seconds)
    if time_taken_seconds < 30:
        bonus_xp += 15
    
    total_xp = base_xp + bonus_xp
    
    # Award XP
    xp_result = award_xp(
        user_id=user_id,
        amount=total_xp,
        reason="quiz_completed",
        source="quiz_system",
        category_code=category,
        related_quiz_id=quiz_id,
    )
    
    earned_badges = []
    
    # Check for First Quiz badge
    quiz_count = (
        db.session.query(func.count(func.distinct(XPTransaction.related_quiz_id)))
        .filter(
            XPTransaction.user_id == user_id,
            XPTransaction.reason == "quiz_completed",
            XPTransaction.related_quiz_id.isnot(None),
        )
        .scalar()
    )
    
    if quiz_count == 1:  # First quiz just completed
        first_badge = Badge.query.filter_by(code="FIRST_QUIZ", is_active=True).first()
        if first_badge:
            existing = UserBadge.query.filter_by(user_id=user_id, badge_id=first_badge.id).first()
            if not existing:
                user_badge = UserBadge(
                    user_id=user_id,
                    badge_id=first_badge.id,
                    source="quiz_completion",
                    related_quiz_id=quiz_id,
                )
                db.session.add(user_badge)
                earned_badges.append({
                    "code": first_badge.code,
                    "name": first_badge.name,
                    "description": first_badge.description,
                    "icon": first_badge.icon_url,
                })
    
    # Perfect Score badge
    if percentage == 100.0:
        perfect_badge = Badge.query.filter_by(code="PERFECT_SCORE", is_active=True).first()
        if perfect_badge:
            existing = UserBadge.query.filter_by(user_id=user_id, badge_id=perfect_badge.id).first()
            if not existing:
                user_badge = UserBadge(
                    user_id=user_id,
                    badge_id=perfect_badge.id,
                    source="quiz_completion",
                    related_quiz_id=quiz_id,
                )
                db.session.add(user_badge)
                earned_badges.append({
                    "code": perfect_badge.code,
                    "name": perfect_badge.name,
                    "description": perfect_badge.description,
                    "icon": perfect_badge.icon_url,
                })
    
    # Speed Master badge
    if time_taken_seconds < 30:
        speed_badge = Badge.query.filter_by(code="SPEED_MASTER", is_active=True).first()
        if speed_badge:
            existing = UserBadge.query.filter_by(user_id=user_id, badge_id=speed_badge.id).first()
            if not existing:
                user_badge = UserBadge(
                    user_id=user_id,
                    badge_id=speed_badge.id,
                    source="quiz_completion",
                    related_quiz_id=quiz_id,
                )
                db.session.add(user_badge)
                earned_badges.append({
                    "code": speed_badge.code,
                    "name": speed_badge.name,
                    "description": speed_badge.description,
                    "icon": speed_badge.icon_url,
                })

    # Update streak tracking
    streak_info = update_streak(user_id)
    
    # Check and award streak badges
    streak_badges = check_streak_badges(user_id, streak_info["current_streak"])
    if streak_badges:
        earned_badges.extend(streak_badges)
    
    # Update category progress
    category_info = update_category_progress(user_id, category)
    
    # Check and award category mastery badge
    mastery_badge = check_category_mastery_badge(user_id, category, category_info["quizzes_completed"])
    if mastery_badge:
        earned_badges.append(mastery_badge)
    
    db.session.commit()
    
    # Get updated level info
    level_info = get_level_progress(xp_result["new_total_xp"])
    
    return jsonify({
        "message": "Quiz completed successfully",
        "xp_gained": total_xp,
        "base_xp": base_xp,
        "bonus_xp": bonus_xp,
        "new_total_xp": xp_result["new_total_xp"],
        "new_level": level_info["level"],
        "progress_pct": level_info["progress_pct"],
        "percentage": round(percentage, 2),
        "earned_badges": earned_badges,
        "streak": streak_info,
        "category_progress": category_info,
        "quizzes_completed": quiz_count or 0,
    }), 200


# Error handling decorator
def handle_errors(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ValueError as e:
            logger.warning(f"Validation error in {func.__name__}: {str(e)}")
            return jsonify({"error": "Validation error", "message": str(e)}), 400
        except Exception as e:
            logger.error(f"Unexpected error in {func.__name__}: {str(e)}", exc_info=True)
            return jsonify({"error": "Internal server error", "message": str(e)}), 500
    wrapper.__name__ = func.__name__
    return wrapper


# Health check endpoint
@gamification_bp.route("/health", methods=["GET"])
def health_check():
    try:
        # Check database connection
        db.session.execute("SELECT 1")
        return jsonify({
            "status": "healthy",
            "database": "connected",
            "timestamp": datetime.utcnow().isoformat()
        }), 200
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return jsonify({
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e)
        }), 503
        return jsonify({"error": str(e)}), 500
