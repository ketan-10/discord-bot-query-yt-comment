FROM python:3.10.5-buster

WORKDIR /

COPY Pipfile .
COPY Pipfile.lock .

RUN pip install pipenv
RUN pipenv install --system --deploy --ignore-pipfile

COPY . .

CMD ["python","-u" ,"src/main.py"]