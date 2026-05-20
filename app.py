from flask import Flask, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
from web3 import Web3
from werkzeug.security import generate_password_hash, check_password_hash
import os
import datetime
import random
import threading
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
CORS(app)

# Khóa luồng (Lock) để giải quyết lỗi 2 người đẩy Blockchain cùng lúc
tx_lock = threading.Lock()

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

def get_vn_time():
    vn_time = datetime.datetime.utcnow() + datetime.timedelta(hours=7)
    return vn_time.strftime("%d/%m/%Y %H:%M")

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

@app.route('/api/forgot-password', methods=['POST'])
def forgot_password():
    try:
        data = request.json
        phone = data.get("phone", "").strip()
        new_password = data.get("new_password", "")
        
        if not phone or not new_password:
            return jsonify({"status": "error", "message": "Vui lòng truyền đủ thông tin!"}), 400

        user = users_collection.find_one({"phone": phone})
        if not user:
            return jsonify({"status": "error", "message": "Số điện thoại chưa được đăng ký!"}), 404
            
        hashed_new_password = generate_password_hash(new_password)
        users_collection.update_one({"_id": user["_id"]}, {"$set": {"password": hashed_new_password}})
        
        return jsonify({"status": "success", "message": "Cập nhật mật khẩu thành công!", "username": user["username"]}), 200
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
        ma_lo = data.get("ma_lo", "").strip()
        flower_name = data.get("flower_name", "").strip()
        ten_vuon = data.get("ten_vuon", "").strip()
        ngay_thu = data.get("ngay_thu", "").strip()
        khu_vuc = data.get("khu_vuc", "").strip()
        weight = int(data.get("weight", 0))
        gia_ban = data.get("gia_ban", "").strip()
        quality = data.get("quality", "").strip()
        ghi_chu = data.get("ghi_chu", "").strip()

        if weight <= 0:
            return jsonify({"status": "error", "message": "Sản lượng không hợp lệ!"}), 400
        
        # Đóng gói thông tin bắn lên Blockchain
        combined_flower_type = f"{ma_lo}|{flower_name}|{ten_vuon}|{quality}|{gia_ban}"
        
        private_key = os.getenv("PRIVATE_KEY")
        contract_address = Web3.to_checksum_address(os.getenv("CONTRACT_ADDRESS"))
        account = w3.eth.account.from_key(private_key)
        contract = w3.eth.contract(address=contract_address, abi=contract_abi)
        
        with tx_lock:
            nonce = w3.eth.get_transaction_count(account.address, 'pending')
            tx = contract.functions.addHarvest(farmer, combined_flower_type, weight).build_transaction({
                'chainId': 11155111, 'gas': 3000000, 'gasPrice': w3.eth.gas_price, 'nonce': nonce
            })
            signed_tx = w3.eth.account.sign_transaction(tx, private_key=private_key)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            tx_hash_hex = w3.to_hex(tx_hash)
        
        current_time = get_vn_time()
        
        harvest_collection.insert_one({
            "farmer": farmer, "ma_lo": ma_lo, "flower_name": flower_name, "ten_vuon": ten_vuon,
            "ngay_thu": ngay_thu, "khu_vuc": khu_vuc, "weight": weight, "gia_ban": gia_ban,
            "quality": quality, "ghi_chu": ghi_chu,
            "flower_type": f"{flower_name} - {quality}", 
            "tx_hash": tx_hash_hex, "date": current_time
        })
        
        return jsonify({"status": "success", "message": f"TxHash: {tx_hash_hex}"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/history', methods=['GET'])
def get_history():
    try:
        farmer = request.args.get("farmer", "").strip().lower()
        records = list(harvest_collection.find({"farmer": farmer}).sort("_id", -1))
        for r in records:
            r["_id"] = str(r["_id"])
        return jsonify({"status": "success", "records": records}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/stats', methods=['GET'])
def get_stats():
    try:
        farmer = request.args.get("farmer", "").strip().lower()
        user_records = list(harvest_collection.find({"farmer": farmer}))
        
        total_weight = sum(record.get("weight", 0) for record in user_records)
        loai1_weight = sum(record.get("weight", 0) for record in user_records if "Loại 1" in record.get("flower_type", ""))
        
        return jsonify({"status": "success", "total_weight": total_weight, "loai1_weight": loai1_weight}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/weather', methods=['GET'])
def get_weather():
    weather_conditions = [
        {"day": "Hôm nay", "temp": "28°C", "humidity": "65%", "status": "Trời nắng đẹp", "recommendation": "Rất thuận lợi để thu hoạch cúc đại đóa. Hoa sẽ đạt phẩm chất màu sắc tốt nhất.", "icon": "☀️", "color": "#059669"},
        {"day": "Ngày mai", "temp": "33°C", "humidity": "50%", "status": "Nắng gắt", "recommendation": "Nên thu hoạch vào sáng sớm hoặc chiều mát. Tránh khung giờ trưa để hoa không bị héo nát.", "icon": "🌤️", "color": "#d97706"},
        {"day": "Ngày kia", "temp": "24°C", "humidity": "88%", "status": "Mưa rào rải rác", "recommendation": "Cân nhắc hoãn thu hoạch. Hoa dính nước mưa dễ bị úng và nấm mốc khi đóng gói vận chuyển.", "icon": "🌧️", "color": "#ef4444"}
    ]
    return jsonify({"status": "success", "forecast": weather_conditions}), 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
