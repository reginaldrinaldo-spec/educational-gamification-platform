# analytics_routes.py

import logging
from datetime import datetime, date

from flask import Blueprint, jsonify, request, current_app
from sqlalchemy import func, cast, Date

from gamification_models import (
    db,
    User,
    Quiz,
    QuizAttempt,
    Badge,
    UserBadge,
    XPTransaction,
    LeaderboardEntry,
)

# -------------------------------------------------------------------
# Blueprint definition
# -------------------------------------------------------------------

analytics_bp = Blueprint("analytics_bp", __name__, url_prefix="/api/analytics")

# -------------------------------------------------------------------
# Logging configuration
# -------------------------------------------------------------------

logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

logger.setLevel(logging.INFO)


# -------------------------------------------------------------------
# Local models for analytics (error logs + API performance)
# -------------------------------------------------------------------

class ErrorLog(db.Model):
    __tablename__ = "error_logs"

    id = db.Column(db.Integer, primary_key=True)
    error_type = db.Column(db.String(255), nullable=False)
    error_message = db.Column(db.Text, nullable=False)
    stack_trace = db.Column(db.Text, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship("User", backref="error_logs", lazy="joined")


class ApiRequestLog(db.Model):
    """
    Optional helper model to support /performance endpoint.

    You can populate this table in a before_request / after_request hook
    elsewhere in the app.
    """
    __tablename__ = "api_request_logs"

    id = db.Column(db.Integer, primary_key=True)
    endpoint = db.Column(db.String(255), nullable=False)
    method = db.Column(db.String(10), nullable=False)
    status_code = db.Column(db.Integer, nullable=False)
    duration_ms = db.Column(db.Float, nullable=False)
    db_duration_ms = db.Column(db.Float, nullable=True)
    is_error = db.Column(db.Boolean, default=False, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def _json_error(message, status_code=400, extra=None):
    payload = {"status": "error", "message": message}
    if extra:
        payload.update(extra)
    return jsonify(payload), status_code


def _today_utc_range():
    """Returns (start_datetime, end_datetime) for current UTC day."""
    today = date.today()
    start = datetime.combine(today, datetime.min.time())
    end = datetime.combine(today, datetime.max.time())
    return start, end


# -------------------------------------------------------------------
# 1. GET /activity/<user_id>
#    - Total quizzes taken
#    - Average score
#    - Last activity timestamp
#    - Active days count
# -------------------------------------------------------------------

@analytics_bp.route("/activity/<int:user_id>", methods=["GET"])
def get_user_activity(user_id: int):
    try:
        user = User.query.get(user_id)
        if not user:
            return _json_error("User not found", status_code=404)

        # Total quizzes taken (assuming each QuizAttempt represents a taken quiz)
        total_quizzes_taken = QuizAttempt.query.filter_by(user_id=user_id).count()

        # Average score
        avg_score_query = db.session.query(func.avg(QuizAttempt.score)).filter(
            QuizAttempt.user_id == user_id
        )
        average_score = avg_score_query.scalar()
        if average_score is not None:
            average_score = float(average_score)

        # Last activity timestamp (last completed / attempted quiz)
        last_activity_query = db.session.query(
            func.max(
                getattr(
                    QuizAttempt,
                    "completed_at",
                    getattr(QuizAttempt, "created_at", QuizAttempt.id),
                )
            )
        ).filter(QuizAttempt.user_id == user_id)
        last_activity = last_activity_query.scalar()

        # Active days count: distinct days where there is at least one attempt
        timestamp_field = getattr(
            QuizAttempt, "completed_at", getattr(QuizAttempt, "created_at", None)
        )
        if timestamp_field is not None:
            active_days_count_query = db.session.query(
                func.count(
                    func.distinct(
                        cast(timestamp_field, Date)
                    )
                )
            ).filter(QuizAttempt.user_id == user_id)
            active_days_count = active_days_count_query.scalar() or 0
        else:
            active_days_count = 0

        response = {
            "status": "success",
            "data": {
                "user_id": user_id,
                "total_quizzes_taken": total_quizzes_taken,
                "average_score": average_score,
                "last_activity_timestamp": last_activity.isoformat()
                if isinstance(last_activity, datetime)
                else None,
                "active_days_count": int(active_days_count),
            },
        }
        return jsonify(response), 200

    except Exception as e:
        logger.exception("Error in /activity/%s endpoint", user_id)
        return _json_error("Internal server error", status_code=500)


# -------------------------------------------------------------------
# 2. GET /performance
#    - API response times (avg, min, max)
#    - Total requests today
#    - Error rate
#    - Database query performance
# -------------------------------------------------------------------

@analytics_bp.route("/performance", methods=["GET"])
def get_performance_metrics():
    try:
        start_today, end_today = _today_utc_range()

        # Query today's request logs
        logs_today = ApiRequestLog.query.filter(
            ApiRequestLog.timestamp >= start_today,
            ApiRequestLog.timestamp <= end_today,
        )

        total_requests_today = logs_today.count()

        if total_requests_today == 0:
            # No data yet — return empty metrics but still success
            response = {
                "status": "success",
                "data": {
                    "response_times": {
                        "average_ms": None,
                        "min_ms": None,
                        "max_ms": None,
                    },
                    "total_requests_today": 0,
                    "error_rate": None,
                    "db_performance": {
                        "average_ms": None,
                        "min_ms": None,
                        "max_ms": None,
                    },
                },
            }
            return jsonify(response), 200

        # Response times
        rt_stats = db.session.query(
            func.avg(ApiRequestLog.duration_ms),
            func.min(ApiRequestLog.duration_ms),
            func.max(ApiRequestLog.duration_ms),
        ).filter(
            ApiRequestLog.timestamp >= start_today,
            ApiRequestLog.timestamp <= end_today,
        ).one()

        avg_rt, min_rt, max_rt = rt_stats

        # Error rate
        error_count = logs_today.filter(ApiRequestLog.is_error.is_(True)).count()
        error_rate = error_count / float(total_requests_today) if total_requests_today else None

        # DB performance (ignore nulls)
        db_perf_stats = db.session.query(
            func.avg(ApiRequestLog.db_duration_ms),
            func.min(ApiRequestLog.db_duration_ms),
            func.max(ApiRequestLog.db_duration_ms),
        ).filter(
            ApiRequestLog.timestamp >= start_today,
            ApiRequestLog.timestamp <= end_today,
            ApiRequestLog.db_duration_ms.isnot(None),
        ).one()

        avg_db, min_db, max_db = db_perf_stats

        response = {
            "status": "success",
            "data": {
                "response_times": {
                    "average_ms": float(avg_rt) if avg_rt is not None else None,
                    "min_ms": float(min_rt) if min_rt is not None else None,
                    "max_ms": float(max_rt) if max_rt is not None else None,
                },
                "total_requests_today": int(total_requests_today),
                "error_rate": float(error_rate) if error_rate is not None else None,
                "db_performance": {
                    "average_ms": float(avg_db) if avg_db is not None else None,
                    "min_ms": float(min_db) if min_db is not None else None,
                    "max_ms": float(max_db) if max_db is not None else None,
                },
            },
        }
        return jsonify(response), 200

    except Exception as e:
        logger.exception("Error in /performance endpoint")
        return _json_error("Internal server error", status_code=500)


# -------------------------------------------------------------------
# 3. POST /log-error
#    - Stores error logs in database
# -------------------------------------------------------------------

@analytics_bp.route("/log-error", methods=["POST"])
def log_error():
    try:
        data = request.get_json(silent=True) or {}

        error_type = data.get("error_type")
        error_message = data.get("error_message")
        stack_trace = data.get("stack_trace")
        user_id = data.get("user_id")

        if not error_type or not error_message:
            return _json_error(
                "Fields 'error_type' and 'error_message' are required", status_code=400
            )

        # If user_id is provided, validate that the user exists
        user = None
        if user_id is not None:
            user = User.query.get(user_id)
            if not user:
                return _json_error("Provided user_id does not exist", status_code=400)

        error_log = ErrorLog(
            error_type=error_type,
            error_message=error_message,
            stack_trace=stack_trace,
            user_id=user.id if user else None,
            timestamp=datetime.utcnow(),
        )

        db.session.add(error_log)
        db.session.commit()

        logger.error(
            "Logged error: type=%s, user_id=%s, message=%s",
            error_type,
            user_id,
            error_message,
        )

        response = {
            "status": "success",
            "data": {
                "error_id": error_log.id,
                "timestamp": error_log.timestamp.isoformat(),
            },
        }
        return jsonify(response), 201

    except Exception as e:
        logger.exception("Error in /log-error endpoint")
        db.session.rollback()
        return _json_error("Internal server error", status_code=500)


# -------------------------------------------------------------------
# 4. GET /metrics
#    - DAU
#    - Quiz completion rate
#    - Average score per quiz
#    - Badge unlock rates
#    - Leaderboard activity
# -------------------------------------------------------------------

@analytics_bp.route("/metrics", methods=["GET"])
def get_platform_metrics():
    try:
        start_today, end_today = _today_utc_range()

        # --------------------------
        # Daily Active Users (DAU)
        # --------------------------
        qa_timestamp_field = getattr(
            QuizAttempt, "completed_at", getattr(QuizAttempt, "created_at", None)
        )
        if qa_timestamp_field is not None:
            dau_query = db.session.query(
                func.count(func.distinct(QuizAttempt.user_id))
            ).filter(
                qa_timestamp_field >= start_today,
                qa_timestamp_field <= end_today,
            )
            daily_active_users = dau_query.scalar() or 0
        else:
            daily_active_users = 0

        # --------------------------
        # Quiz completion rate
        # --------------------------
        total_attempts = QuizAttempt.query.count()

        completion_rate = None
        if total_attempts > 0:
            # If the model has a boolean completion flag, use it
            if hasattr(QuizAttempt, "is_completed"):
                completed_attempts = QuizAttempt.query.filter_by(
                    is_completed=True
                ).count()
                completion_rate = completed_attempts / float(total_attempts)
            elif hasattr(QuizAttempt, "status"):
                # If there is a status field, assume 'completed' marks completion
                completed_attempts = QuizAttempt.query.filter(
                    QuizAttempt.status == "completed"
                ).count()
                completion_rate = completed_attempts / float(total_attempts)
            else:
                # Fallback: assume all QuizAttempt rows represent completed quizzes
                completion_rate = 1.0

        # --------------------------
        # Average score per quiz
        # --------------------------
        avg_scores_per_quiz = []
        if hasattr(QuizAttempt, "score") and hasattr(QuizAttempt, "quiz_id"):
            scores_query = (
                db.session.query(
                    QuizAttempt.quiz_id, func.avg(QuizAttempt.score).label("avg_score")
                )
                .group_by(QuizAttempt.quiz_id)
                .all()
            )
            for quiz_id, avg_score in scores_query:
                avg_scores_per_quiz.append(
                    {
                        "quiz_id": quiz_id,
                        "average_score": float(avg_score) if avg_score is not None else None,
                    }
                )

        global_avg_score = None
        if avg_scores_per_quiz:
            # global average of all attempts
            global_avg_score_val = db.session.query(
                func.avg(QuizAttempt.score)
            ).scalar()
            if global_avg_score_val is not None:
                global_avg_score = float(global_avg_score_val)

        # --------------------------
        # Badge unlock rates
        # --------------------------
        total_users = User.query.count()
        badge_unlock_rates = []

        if total_users > 0:
            badge_counts = (
                db.session.query(
                    UserBadge.badge_id,
                    func.count(func.distinct(UserBadge.user_id)).label("unlocked_users"),
                )
                .group_by(UserBadge.badge_id)
                .all()
            )

            badge_map = {b.id: b for b in Badge.query.all()}

            for badge_id, unlocked_users in badge_counts:
                badge = badge_map.get(badge_id)
                rate = unlocked_users / float(total_users) if total_users else None
                badge_unlock_rates.append(
                    {
                        "badge_id": badge_id,
                        "badge_name": getattr(badge, "name", None),
                        "unlocked_users": int(unlocked_users),
                        "unlock_rate": float(rate) if rate is not None else None,
                    }
                )

        # --------------------------
        # Leaderboard activity
        # --------------------------
        lb_timestamp_field = getattr(
            LeaderboardEntry,
            "updated_at",
            getattr(LeaderboardEntry, "created_at", None),
        )

        total_leaderboard_entries = LeaderboardEntry.query.count()

        leaderboard_activity_today = 0
        if lb_timestamp_field is not None:
            leaderboard_activity_today = (
                db.session.query(func.count(LeaderboardEntry.id))
                .filter(
                    lb_timestamp_field >= start_today,
                    lb_timestamp_field <= end_today,
                )
                .scalar()
                or 0
            )

        response = {
            "status": "success",
            "data": {
                "daily_active_users": int(daily_active_users),
                "quiz_completion_rate": float(completion_rate)
                if completion_rate is not None
                else None,
                "average_score": {
                    "global_average_score": global_avg_score,
                    "per_quiz": avg_scores_per_quiz,
                },
                "badge_unlock_rates": badge_unlock_rates,
                "leaderboard_activity": {
                    "total_entries": int(total_leaderboard_entries),
                    "entries_today": int(leaderboard_activity_today),
                },
            },
        }

        return jsonify(response), 200

    except Exception as e:
        logger.exception("Error in /metrics endpoint")
        return _json_error("Internal server error", status_code=500)
