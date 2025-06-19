from flask import Flask, jsonify
import subprocess

app = Flask(__name__)

@app.post('/start_vpn')
def start_vpn():
    subprocess.run(['wg-quick','up','wg0'])
    return jsonify(ok=True)

# …add /stop_vpn, /check_ip, etc…

if __name__=='__main__':
    app.run(host='0.0.0.0', port=5000)
