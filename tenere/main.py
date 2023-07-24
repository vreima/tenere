from fastapi import FastAPI

app = FastAPI()

@app.route("/")
def root():
    return "Hello, world!"