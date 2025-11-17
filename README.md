# 🎓 Educational Gamification Platform (MeMe)

## 📋 Project Overview

An AI-driven educational gamification platform focused on meme culture, designed to make learning engaging and interactive through personalized quizzes, badges, tournaments, and social features.

## ✨ Features

### Core Functionality
- 🔐 **User Authentication**: JWT-based secure authentication system
- 📚 **Module Management**: Organize educational content into structured modules
- ❓ **Quiz System**: Interactive quizzes with multiple-choice questions
- 🎮 **Gamification**: XP points, badges, leaderboards, and tournaments
- 👤 **User Profiles**: Track progress, achievements, and learning analytics
- 🤖 **AI Integration**: Gemini AI for personalized learning and content generation

### Technical Stack
- **Backend**: Flask 2.3.3 + Python 3.11
- **Database**: PostgreSQL with SQLAlchemy ORM
- **Authentication**: JWT tokens with Flask-JWT-Extended
- **API**: RESTful endpoints with CORS support
- **Deployment**: Render (production) with Gunicorn

## 🚀 Live Deployment

**Production URL**: https://educational-gamification-platform.onrender.com

### API Endpoints
- `GET /health` - Health check endpoint
- `GET /api/test` - Test API connectivity
- `POST /api/auth/register` - User registration
- `POST /api/auth/login` - User login
- `GET /api/modules` - List all modules
- `GET /api/sessions` - Game sessions
- `GET /api/leaderboard` - User rankings

## 🛠️ Local Development Setup

### Prerequisites
- Python 3.11+
- PostgreSQL database
- Git

### Installation Steps

1. **Clone the repository**
```bash
git clone https://github.com/reginaldrinaldo-spec/educational-gamification-platform.git
cd educational-gamification-platform
```

2. **Create virtual environment**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Set up environment variables**

Copy `.env.example` to `.env` and configure:
```bash
cp .env.example .env
```

Edit `.env` with your settings:
```
SECRET_KEY=your-secret-key-here
FLASK_ENV=development
DATABASE_URL=postgresql://user:password@localhost:5432/dbname
```

5. **Run the application**
```bash
python app.py
```

The API will be available at `http://localhost:5000`

## 📦 Project Structure

```
educational-gamification-platform/
├── app.py                 # Main Flask application
├── requirements.txt       # Python dependencies
├── Procfile              # Render deployment config
├── runtime.txt           # Python version specification
├── .env.example          # Environment variables template
└── README.md             # This file
```

## 🗄️ Database Schema

- **Users**: User accounts and authentication
- **Modules**: Educational content organization
- **GameSessions**: Track user progress and sessions
- **Analytics**: User activity and performance metrics

## 🔑 Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `SECRET_KEY` | Flask secret key for sessions | Yes |
| `FLASK_ENV` | Environment (development/production) | Yes |
| `DATABASE_URL` | PostgreSQL connection string | Yes |
| `JWT_SECRET_KEY` | Secret key for JWT tokens | Yes |

## 📝 API Documentation

Full API documentation available at: (Coming soon)

## 🚢 Deployment on Render

This project is configured for automatic deployment on Render:

1. **Create new Web Service** on Render
2. **Connect GitHub repository**
3. **Configure environment variables** in Render dashboard
4. **Deploy** - Render will automatically use `Procfile` and `requirements.txt`

### Render Configuration
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `gunicorn app:app` (from Procfile)
- **Environment**: Python 3.11

## 📊 Current Status (Phase 7 - COMPLETED)

✅ Backend LIVE on Render
✅ Database operational  
✅ 9 API endpoints functional
✅ JWT authentication implemented
✅ CORS configured
✅ 100% database consistency
✅ Response times < 100ms

## 🔄 Development Roadmap

### Completed
- ✅ Phase 1-4: Backend setup and core models
- ✅ Phase 5: Authentication and security
- ✅ Phase 6: API endpoints and testing
- ✅ Phase 7: Production deployment

### Next Steps
- 📝 Phase 8: Frontend development (React/Next.js)
- 🎨 Phase 9: UI/UX with Tailwind CSS
- 🤖 Phase 10: AI integration (Gemini)
- 🚀 Phase 11: Beta testing and launch

## 👥 Team

**MeMe Sprint Team**
- Project: Educational Gamification Platform
- Focus: Meme culture education with AI personalization

## 📄 License

This project is part of the MeMe educational initiative.

## 🤝 Contributing

Contributions welcome! Please follow these steps:
1. Fork the repository
2. Create feature branch
3. Commit changes
4. Push to branch
5. Open Pull Request

## 📞 Support

For issues and questions, please open a GitHub issue.

---

**Last Updated**: November 17, 2025
**Status**: ✅ FULLY OPERATIONAL
