# Heroku-style process definitions (also understood by Railway/Fly).
#
# NOTE: each Heroku app exposes ONE public "web" process. To run both the
# API and the dashboard on Heroku, deploy two apps from this repo:
#   API app       -> uses this Procfile's "web" + "release" lines
#   Dashboard app -> same repo, but its Procfile "web" line should be the
#                    streamlit command from the "dashboard" line below
#
# On Railway/Render/Fly you can instead define two services from one repo
# and set their start commands to these same lines (see DEPLOYMENT.md).

release: alembic upgrade head
web: uvicorn backend.main:app --host 0.0.0.0 --port $PORT --workers 2
dashboard: streamlit run frontend/app.py --server.port $PORT --server.address 0.0.0.0 --server.headless true --browser.gatherUsageStats false
