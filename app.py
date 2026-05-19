from flask import Flask, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
from web3 import Web3
from werkzeug.security import generate_password_hash, check_password_hash
import os
import datetime
import random
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
CORS(app)

# 1. KẾT NỐI MONGODB CLOUD
try:
    client = MongoClient(os.getenv("MONGODB_URI"), serverSelectionTimeoutMS=5000)
    db = client["PBL5_Farm"]
    harvest_collection = db["harvest_records"]
    users_collection = db["users_account"]
    print("✅ Đã kết nối MongoDB Cloud!")
except Exception as e:
    print("❌ Lỗi MongoDB:", e)

# 2. KẾT NỐI WEB3 BLOCKCHAIN
try:
    rpc_url = os.getenv("WEB3_RPC_URL", "https://sepolia.drpc.org")
    w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={'timeout': 10}))
    if w3.is_connected():
        print("✅ Đã kết nối Web3 (Sepolia)")
except Exception as e:
    print("❌ Lỗi Web3:", e)

contract_abi = [
    {
        "inputs": [
            {"internalType": "string", "name": "_farmer", "type": "string"},
            {"internalType": "string", "name": "_flowerType", "type": "string"},
            {"internalType": "uint256", "name": "_weight", "type": "uint256"}
        ],
        "name": "addHarvest",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]

@app.route('/api/register', methods=['POST'])
def register():
    try:
        data = request.json
        username = data.get("username", "").strip().lower()
        password = data.get("password", "")
        fullname = data.get("fullname", "").strip()
        location = data.get("location", "").strip()
        phone = data.get("phone", "").strip()

        if not username or not password or not fullname or not location or not phone:
            return jsonify({"status": "error", "message": "Vui lòng điền đầy đủ thông tin!"}), 400

        if users_collection.find_one({"username": username}):
            return jsonify({"status": "error", "message": "Tài khoản đăng ký đã tồn tại!"}), 400
            
        if users_collection.find_one({"phone": phone}):
            return jsonify({"status": "error", "message": "Số điện thoại này đã được sử dụng!"}), 400

        hashed_password = generate_password_hash(password)
        farmer_id = f"FAR_{random.randint(1000, 9999)}"
        join_date = datetime.date.today().strftime("%d/%m/%Y")

        users_collection.insert_one({
            "username": username,
            "password": hashed_password,
            "fullname": fullname,
            "location": location,
            "phone": phone,
            "farmer_id": farmer_id,
            "join_date": join_date
        })

        return jsonify({"status": "success", "message": "Đăng ký thành công!"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# API: QUÊN MẬT KHẨU (CHỈ CẦN SỐ ĐIỆN THOẠI)
@app.route('/api/forgot-password', methods=['POST'])
def forgot_password():
    try:
        data = request.json
        phone = data.get("phone", "").strip()
        new_password = data.get("new_password", "")
        
        if not phone or not new_password:
            return jsonify({"status": "error", "message": "Vui lòng truyền đủ thông tin!"}), 400

        # Chỉ dùng số điện thoại để tìm người dùng
        user = users_collection.find_one({"phone": phone})
        
        if not user:
            return jsonify({"status": "error", "message": "Số điện thoại chưa được đăng ký trong hệ thống!"}), 404
            
        hashed_new_password = generate_password_hash(new_password)
        
        users_collection.update_one(
            {"_id": user["_id"]}, 
            {"$set": {"password": hashed_new_password}}
        )
        
        # Trả về kèm theo username để nhắc cho người dùng nhớ
        return jsonify({
            "status": "success", 
            "message": "Cập nhật mật khẩu thành công!",
            "username": user["username"] 
        }), 200
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.json
        username = data.get("username", "").strip().lower()
        password = data.get("password", "")
        
        user = users_collection.find_one({"username": username})
        
        if user and check_password_hash(user["password"], password):
            return jsonify({
                "status": "success", "username": username, "fullname": user.get("fullname"),
                "location": user.get("location"), "farmer_id": user.get("farmer_id"),
                "join_date": user.get("join_date")
            }), 200
        else:
            return jsonify({"status": "error", "message": "Sai tài khoản hoặc mật khẩu!"}), 401
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/harvest', methods=['POST'])
def add_harvest():
    try:
        data = request.json
        farmer = data.get("farmer").strip().lower()
        flower_type = data.get("flower_type")
        weight = int(data.get("weight"))
        
        harvest_collection.insert_one({"farmer": farmer, "flower_type": flower_type, "weight": weight})
        
        private_key = os.getenv("PRIVATE_KEY")
        contract_address = Web3.to_checksum_address(os.getenv("CONTRACT_ADDRESS"))
        account = w3.eth.account.from_key(private_key)
        contract = w3.eth.contract(address=contract_address, abi=contract_abi)
        
        nonce = w3.eth.get_transaction_count(account.address)
        tx = contract.functions.addHarvest(farmer, flower_type, weight).build_transaction({
            'chainId': 11155111, 'gas': 3000000, 'gasPrice': w3.eth.gas_price, 'nonce': nonce
        })
        signed_tx = w3.eth.account.sign_transaction(tx, private_key=private_key)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        
        return jsonify({"status": "success", "message": f"TxHash: {w3.to_hex(tx_hash)}"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/stats', methods=['GET'])
def get_stats():
    try:
        farmer = request.args.get("farmer", "").strip().lower()
        user_records = list(harvest_collection.find({"farmer": farmer}))
        total_weight = sum(record.get("weight", 0) for record in user_records)
        return jsonify({"status": "success", "total_weight": total_weight}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    # Ra lệnh cho Python: Nếu ở trên mây thì lấy Port của mây, nếu ở máy tính thì lấy 5000
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)