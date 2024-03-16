import logging.config
import uuid

from pydantic import BaseModel
from datetime import timedelta
from flask import Flask, jsonify, request, make_response
from flask_jwt_extended import JWTManager, jwt_required, create_access_token, get_jwt_identity
from concurrent.futures import ThreadPoolExecutor

from .scraper import get_data

import threading

semaphore_for_driver = threading.BoundedSemaphore(5)
semaphore_for_redis = threading.BoundedSemaphore(10)

class Body(BaseModel):
    id: uuid.UUID = uuid.uuid4()
    links: list
    in_thread_options: dict
    num_tabs: str = 4

class ParseOptions(BaseModel):
    scroll: bool
    scroll_amount: int = None
    slow: bool = None

def group_in_tabs(lst, n):
    return [lst[i:i + n] for i in range(0, len(lst), n)]

logging.config.fileConfig('logging.conf')
logger = logging.getLogger("root")

app = Flask(__name__)
executor = ThreadPoolExecutor(max_workers=20) # i will need a solution to set it up from API
tasks = {}
app.config['JWT_SECRET_KEY'] = 'EUFaS8JQg34eFDeuY6pUJGE2XMCYGbKK'
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=12)
jwt = JWTManager(app)

USERNAME = 'admin'
PASSWORD = 'asdre123'

@app.before_request
def before_request_callback():
    if request.method == 'POST':
        if 'Content-Type' not in request.headers:
            return jsonify({"msg": "Content-Type header is required"}), 400
        elif request.headers['Content-Type'] != 'application/json':
            return jsonify({"msg": "Request header must be application/json"}), 400

@app.route('/login', methods=['POST'])
def login():
    username = request.json.get('username', None)
    password = request.json.get('password', None)
    if username == USERNAME and password == PASSWORD:
        access_token = create_access_token(identity=username)
        return jsonify(access_token=f'Bearer {access_token}')
    else:
        return jsonify({"msg": "Bad username or password"}), 401


@app.route("/", methods=['POST'])
@jwt_required()
def disperse_threads():
    current_user = get_jwt_identity()
    try:
        received_data = request.get_json()
        request_obj = Body(**received_data)
    except:
        return jsonify(result="Error reading request body"), 400
    request_obj.id = uuid.uuid4()
    links = group_in_tabs(request_obj.links, request_obj.num_tabs)
    parse_options = ParseOptions(**request_obj.in_thread_options)
    for batch in links:
        future = executor.submit(get_data, id=request_obj.id, parse_options=parse_options, 
                                group_of_tabs=batch, total_num=len(request_obj.links), semaphore_for_driver=semaphore_for_driver,
                                semaphore_for_redis=semaphore_for_redis)
    tasks[request_obj.id] = future
    return jsonify({'success': True, 'uuid': request_obj.id, 'username': current_user}), 200

@app.errorhandler(400)
def bad_request(error):
    return make_response(jsonify({'error': 'Bad request'}), 400)

@app.errorhandler(401)
def unauthorized(error):
    return make_response(jsonify({'error': 'Unauthorized access'}), 401)
