
# CSV-Parser

A simple web app for parsing csv and compressing the images by 50% of its original quality.

## Documentation

This is a web app that takes a csv with a particular format (see input.csv for reference), process the image (as described in the description) and return the processed output (see output.csv for reference).

Furthermore, See Component Explaination.doc for component-wise info and visual.jpg for a visual understanding.


## Tech Stack

**Server:** Python, Flask

**Database:** MySQL

**Cloud Storage:** Cloudinary

**Background Task:** Celery, Redis



## Run Locally

Clone the project

```bash
  https://github.com/paras41617/CSV-Parser
```

Go to the project directory

```bash
  cd CSV-Parser
```

Install dependencies

```bash
  pip install requirements.txt (using a virtualenv is recommended)
```

Create .env file

```bash
  Add required credentials in the .env file (Look env_example.txt file for reference.)
```

Start Redis

```bash
  Use either Docker or local terminal for starting redis.
  Docker : 

  docker run --name csv_parse_redis_container -p 6379:6379 -d redis

  CELERY_BROKER_URL=redis://localhost:6379/0
  CELERY_RESULT_BACKEND=redis://localhost:6379/0
```

Start the server

```bash
  python app.py
```

Start Celery Worker (In another terminal)

```bash
  celery -A app.tasks worker --loglevel=info -P solo
```