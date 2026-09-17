@echo off
rem Git-обёртка для этого проекта.
rem Папка принадлежит другому пользователю Windows, поэтому git требует явного
rem разрешения safe.directory — иначе он отказывается работать с репозиторием.
git -c safe.directory=D:/disk256/gigaide/aila/aila_web -C "%~dp0.." %*
