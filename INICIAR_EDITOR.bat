@echo off
title Editor de Videos con IA
echo ========================================================
echo   Iniciando Editor de Videos con IA (Desktop App)
echo ========================================================
echo.
python main.py
if %errorlevel% neq 0 (
    echo.
    echo Ocurrio un error al ejecutar la aplicacion.
    pause
)
