@echo off
echo Installing packages...
pip install -r requirements.txt
echo.
echo Creating database...
python setup_db.py
pause
