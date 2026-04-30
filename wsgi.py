"""WSGI entry point for Vercel deployment"""
from app import app

if __name__ == "__main__":
    app.run()
