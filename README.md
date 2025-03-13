# Python Community Project

A Django-based web application that leverages Google's Generative AI (Gemini) to create an interactive community platform.

## 🚀 Features

- Django web framework
- Integration with Google's Generative AI (Gemini)
- Environment variable configuration
- SQLite database (for development)

## 📋 Prerequisites

- Python 3.11+
- Django 5.1.7
- Google Gemini API key

## 🛠️ Installation

1. Clone the repository:
```bash
git clone https://github.com/maxmeadowcroft/PythonCommunityProj.git
cd PythonCommunityProj
```

2. Create a virtual environment and activate it:
```bash
python -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create a `.env` file in the root directory and add your Gemini API key:
```
GEMINI_API_KEY=your_api_key_here
```

5. Run database migrations:
```bash
python manage.py migrate
```

6. Start the development server:
```bash
python manage.py runserver
```

The application will be available at `http://localhost:8000`

## 🔧 Environment Variables

- `GEMINI_API_KEY`: Your Google Gemini API key (required)

## 📦 Project Structure

```
PythonCommunityProj/
├── manage.py
├── requirements.txt
├── .env
├── python_puzzle/      # Main Django project directory
├── puzzle/            # Django app directory
├── templates/         # HTML templates
├── static/           # Static files (CSS, JS, images)
└── venv/             # Virtual environment
```

## 🔑 Getting a Gemini API Key

1. Visit the [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Create or sign in to your Google account
3. Generate an API key
4. Add the key to your `.env` file

## 🤝 Contributing

1. Fork the repository
2. Create a new branch
3. Make your changes
4. Submit a pull request

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## ⚠️ Important Notes

- Never commit your `.env` file or expose your API keys
- The project uses SQLite for development; consider using PostgreSQL for production
- Keep your dependencies updated for security
