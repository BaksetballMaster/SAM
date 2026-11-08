# SAM
High/Middle School Students need access to more resources to enhance their High School Learning journey without explicitly providing answers for tasks and assignments. SAM provides learning resources, sports and volunteering opportunities.

## Run the frontend

The frontend is written in Python (Flask). It uses sample data until a backend is built; see [`SAM_Backend/README.md`](SAM_Backend/README.md) for the API it expects.

```sh
cd SAM_Frontend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Then open http://localhost:5000.

| File | What it does |
|---|---|
| `app.py` | One route per page, sign-in steps and the chat |
| `api.py` | Every data call, with sample data. Each function names the backend endpoint it stands for. |
| `templates/` | The pages (Jinja templates). `base.html` holds the header and the add-resource dialog. |
| `static/styles.css` | The styles |
