from flask import Flask, render_template, request,jsonify
from utils import get_db_connection
import boto3
import os
import json
from dotenv import load_dotenv
from flask import redirect, url_for
from flask_jwt_extended import(
    JWTManager, create_access_token, jwt_required,
    get_jwt_identity
)
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import timedelta

# Load environment variables from .env
load_dotenv()
app = Flask(__name__)

app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=1)
jwt = JWTManager(app)


@app.route('/signup', methods=['POST'])
def signup():
    data = request.json
    required_fields = ['username', 'email', 'password']
    if not all(field in data for field in required_fields):
        return jsonify({'error': 'Missing fields'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM users WHERE username = :username", {'username': data['username']})
        if cursor.fetchone():
            return jsonify({'error': 'Username already exists'}), 409

        hashed_pw = generate_password_hash(data['password'])

        cursor.execute("""
            INSERT INTO users (username, email, password)
            VALUES (:username, :email, :password)
        """, {
            'username': data['username'],
            'email': data['email'],
            'password': hashed_pw
        })
        conn.commit()
        return jsonify({'message': 'User registered successfully'}), 201
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


@app.route('/login', methods=['POST'])
def login():
    data = request.json
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT username, password FROM users WHERE username = :username", {
            'username': data['username']
        })
        user = cursor.fetchone()

        if not user or not check_password_hash(user[1], data['password']):
            return jsonify({'error': 'Invalid username or password'}), 401
        print(type(user[0]))
        user = user[0]
        access_token = create_access_token(identity={'username':user})
        return jsonify({'access_token': access_token}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


@app.route('/forgot-password', methods=['POST'])
def forgot_password():
    data = request.json
    email = data.get('email')

    if not email:
        return jsonify({'error': 'Email is required'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT username FROM users WHERE email = :email", {'email': email})
        user = cursor.fetchone()

        if not user:
            return jsonify({'error': 'Email not found'}), 404

        return jsonify({'message': 'Password reset instructions sent (mock).'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


@app.route('/reset-password', methods=['PUT'])
def reset_password():
    data = request.json
    username = data.get('username')
    new_password = data.get('new_password')

    if not username or not new_password:
        return jsonify({'error': 'Username and new password are required'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        hashed_pw = generate_password_hash(new_password)
        cursor.execute("""
            UPDATE users SET password = :pw WHERE username = :username
        """, {'pw': hashed_pw, 'username': username})
        conn.commit()
        return jsonify({'message': 'Password reset successful'}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/secure-data',  methods=['GET'])
@jwt_required()
def secure_data():
    user = get_jwt_identity()  # {'user_id': ..., 'username': ...}
    #print(user['username'])
    return jsonify({"message": f"Welcome {'username'}!"})


# Initialize Amazon Bedrock Runtime client
bedrock_runtime = boto3.client(
    service_name="bedrock-runtime",
    region_name=os.getenv("AWS_DEFAULT_REGION"),
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY")
)

@app.route('/')
@jwt_required()
def home():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT student_id, first_name, last_name FROM students")
    students = [
        {'student_id': row[0], 'first_name': row[1], 'last_name': row[2]}
        for row in cursor.fetchall()
    ]
    conn.close()
    return json.dumps(students)
    return render_template('home.html', students=students)

@app.route('/student', methods=['GET'])
@jwt_required()
def view_student():
    student_id = request.args.get('sid')
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT s.student_id, s.first_name, s.last_name, s.age, s.gender, s.dob,
               a.height_cm, a.weight_kg, a.skin_tone, a.eye_color, a.hair_color, a.body_type,
               h.blood_type, h.allergies, h.medical_conditions, h.bmi,
               addr.street, addr.city, addr.state, addr.postal_code
        FROM students s
        LEFT JOIN appearance a ON s.student_id = a.student_id
        LEFT JOIN health_stats h ON s.student_id = h.student_id
        LEFT JOIN address addr ON s.student_id = addr.student_id
        WHERE s.student_id = :id
    """, {'id': student_id})

    row = cursor.fetchone()
    conn.close()

    if not row:
        return "No profile found", 404

    keys = [
        'student_id', 'first_name', 'last_name', 'age', 'gender', 'dob',
        'height_cm', 'weight_kg', 'skin_tone', 'eye_color', 'hair_color', 'body_type',
        'blood_type', 'allergies', 'medical_conditions', 'bmi',
        'street', 'city', 'state', 'postal_code'
    ]
    student = dict(zip(keys, row))

    # -------- Generate text profile --------
    prompt = (
        f"Generate a descriptive paragraph for a student profile based on the following details:\n\n"
        f"Name: {student['first_name']} {student['last_name']}\n"
        f"Age: {student['age']}, Gender: {student['gender']}, DOB: {student['dob']}\n"
        f"Height: {student['height_cm']} cm, Weight: {student['weight_kg']} kg, "
        f"Skin tone: {student['skin_tone']}, Eye color: {student['eye_color']}, "
        f"Hair color: {student['hair_color']}, Body type: {student['body_type']}\n"
        f"Blood type: {student['blood_type']}, Allergies: {student['allergies']}, "
        f"Medical Conditions: {student['medical_conditions']}, BMI: {student['bmi']}\n"
        f"Address: {student['street']}, {student['city']}, {student['state']} {student['postal_code']}\n\n"
        f"Write a single coherent paragraph suitable for a profile description."
    )

    try:
        response = bedrock_runtime.invoke_model(
            modelId="amazon.titan-text-express-v1",
            contentType="application/json",
            accept="application/json",
            body=json.dumps({
                "inputText": prompt,
                "textGenerationConfig": {
                    "temperature": 0.7,
                    "maxTokenCount": 300,
                    "topP": 0.9,
                    "stopSequences": []
                }
            })
        )
        body = json.loads(response['body'].read())
        student_profile = body.get("results", [{}])[0].get("outputText", "No profile generated.")
    except Exception as e:
        student_profile = f"Error generating AI profile: {e}"

    try:
        img_prompt = (
            f"A portrait avatar of a {student['gender'].lower()} student, "
            f"{student['age']} years old, "
            f"{student['height_cm']} cm tall, "
            f"{student['skin_tone'].lower()} skin tone, "
            f"{student['eye_color'].lower()} eyes, "
            f"{student['hair_color'].lower()} hair, "
            f"{student['body_type'].lower()} body type, realistic illustration."
        )

        image_body = {
            "taskType": "TEXT_IMAGE",
            "textToImageParams": {
                "text": img_prompt
            },
            "imageGenerationConfig": {
                "numberOfImages": 1,
                "height": 512,
                "width": 512,
                "cfgScale": 7.5,
                "seed": 12345  # optional: use random seed for variation
            }
        }

        img_response = bedrock_runtime.invoke_model(
            modelId="amazon.titan-image-generator-v1",
            contentType="application/json",
            accept="application/json",
            body=json.dumps(image_body)
        )

        img_data = json.loads(img_response['body'].read())
        avatar_b64 = img_data.get("images", [None])[0]
        avatar_data = f"data:image/png;base64,{avatar_b64}" if avatar_b64 else None
    except Exception as e:
        return jsonify({"error":"something went wrong"}), 400

    
    return jsonify({
        "student": student,
        "profile_text": student_profile,
        "avatar_data": avatar_data
    }), 200


@app.route('/add')
@jwt_required()
def add_page():
    return render_template('add_student.html')

@app.route('/add_student', methods=['POST'])
@jwt_required()
def add_student():
    if request.method == 'POST':
        conn = None
        try:
            form = request.form
            
            # Validate required fields
            required_fields = [
                'student_id', 'first_name', 'last_name', 'age', 'gender', 'dob',
                'height_cm', 'weight_kg', 'skin_tone', 'eye_color', 'hair_color', 'body_type',
                'blood_type', 'allergies', 'medical_conditions', 'bmi',
                'street', 'city', 'state', 'postal_code'
            ]
            
            missing_fields = [field for field in required_fields if field not in form]
            if missing_fields:
                return jsonify({
                    "status": "error",
                    "message": f"Missing required fields: {', '.join(missing_fields)}"
                }), 400

            conn = get_db_connection()
            cursor = conn.cursor()

            # Convert date string to Oracle date format
            from datetime import datetime
            dob_date = datetime.strptime(form['dob'], '%Y-%m-%d')  # Assuming input format is YYYY-MM-DD
            oracle_dob = dob_date.strftime('%d-%b-%Y').upper()  # Converts to 'DD-MON-YYYY' format

            # Insert into students (Oracle version)
            cursor.execute("""
                INSERT INTO students (student_id, first_name, last_name, age, gender, dob)
                VALUES (:student_id, :first_name, :last_name, :age, :gender, TO_DATE(:dob, 'DD-MON-YYYY'))
            """, {
                'student_id': form['student_id'],
                'first_name': form['first_name'],
                'last_name': form['last_name'],
                'age': form['age'],
                'gender': form['gender'],
                'dob': oracle_dob  # Using converted date format
            })

            student_id = form['student_id']

            # Insert appearance
            cursor.execute("""
                INSERT INTO appearance (student_id, height_cm, weight_kg, skin_tone, eye_color, hair_color, body_type)
                VALUES (:student_id, :height_cm, :weight_kg, :skin_tone, :eye_color, :hair_color, :body_type)
            """, {
                'student_id': student_id,
                'height_cm': form['height_cm'],
                'weight_kg': form['weight_kg'],
                'skin_tone': form['skin_tone'],
                'eye_color': form['eye_color'],
                'hair_color': form['hair_color'],
                'body_type': form['body_type']
            })

            # Insert health stats
            cursor.execute("""
                INSERT INTO health_stats (student_id, blood_type, allergies, medical_conditions, bmi)
                VALUES (:student_id, :blood_type, :allergies, :medical_conditions, :bmi)
            """, {
                'student_id': student_id,
                'blood_type': form['blood_type'],
                'allergies': form['allergies'],
                'medical_conditions': form['medical_conditions'],
                'bmi': form['bmi']
            })

            # Insert address
            cursor.execute("""
                INSERT INTO address (student_id, street, city, state, postal_code)
                VALUES (:student_id, :street, :city, :state, :postal_code)
            """, {
                'student_id': student_id,
                'street': form['street'],
                'city': form['city'],
                'state': form['state'],
                'postal_code': form['postal_code']
            })

            conn.commit()
            return jsonify({
                "status": "success",
                "message": f"Student {student_id} added successfully"
            }), 201

        except ValueError as e:
            if conn:
                conn.rollback()
            return jsonify({
                "status": "error",
                "message": f"Invalid date format. Please use YYYY-MM-DD. Error: {str(e)}"
            }), 400
        except Exception as e:
            if conn:
                conn.rollback()
            return jsonify({
                "status": "error",
                "message": f"An error occurred: {str(e)}"
            }), 500
        finally:
            if conn:
                conn.close()

    return jsonify({
        "message": "Use POST to add a new student",
        "required_fields": required_fields
    }), 200

# Delete page
@app.route('/delete')
@jwt_required()
def delete_page():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT student_id, first_name, last_name FROM students")
    students = [
        {'student_id': row[0], 'first_name': row[1], 'last_name': row[2]}
        for row in cursor.fetchall()
    ]
    conn.close()
    return render_template('delete.html', students=students)

@app.route('/delete_student', methods=['DELETE'])
@jwt_required()
def delete_student():
    student_id = request.args.get('sid')  # From query string

    if not student_id:
        return "Student ID is required.", 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Delete from ALL child tables first
        cursor.execute("DELETE FROM enrollments WHERE student_id = :id", {'id': student_id})
        cursor.execute("DELETE FROM appearance WHERE student_id = :id", {'id': student_id})
        cursor.execute("DELETE FROM health_stats WHERE student_id = :id", {'id': student_id})
        cursor.execute("DELETE FROM address WHERE student_id = :id", {'id': student_id})
        cursor.execute("DELETE FROM hobbies WHERE student_id = :id", {'id': student_id})

        # Then delete from parent table
        cursor.execute("DELETE FROM students WHERE student_id = :id", {'id': student_id})

        conn.commit()
    except Exception as e:
        conn.rollback()
        return jsonify({"error": f"Error deleting student: {str(e)}"}), 500
    finally:
        conn.close()
    
    return jsonify({"message": f"Student {student_id} deleted successfully."}), 200

@app.route('/update/<int:sid>', methods=['PUT'])
@jwt_required()
def update_student(sid):
    connection = get_db_connection()
    cursor = connection.cursor()

    if request.method == 'PUT':
        # Get updated data from form
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        age = request.form['age']
        gender = request.form['gender']
        bmi = request.form['bmi']
        street = request.form['street']
        city = request.form['city']
        state = request.form['state']
        postal_code = request.form['postal_code']

        if not all([first_name, last_name, age, gender, bmi, street, city, state, postal_code]):
            return jsonify({"error": "Missing one or more required fields"}), 400

        try:
            # Update students
            cursor.execute("""
                UPDATE students SET 
                    first_name = :1, 
                    last_name = :2, 
                    age = :3, 
                    gender = :4
                WHERE student_id = :5
            """, (first_name, last_name, age, gender, sid))

            # Update health_stats
            cursor.execute("""
                UPDATE health_stats SET 
                    bmi = :1
                WHERE student_id = :2
            """, (bmi, sid))

            # Update address
            cursor.execute("""
                UPDATE address SET 
                    street = :1, 
                    city = :2, 
                    state = :3, 
                    postal_code = :4
                WHERE student_id = :5
            """, (street, city, state, postal_code, sid))

            connection.commit()
            return jsonify({"message": f"Student {sid} updated successfully"}), 200
        except Exception as e:
            connection.rollback()
            return jsonify({"error": f"Error during update: {str(e)}"}), 500
        finally:
            cursor.close()
            connection.close()

        return jsonify({"error": "Invalid method"}), 405

    # GET: fetch student info
    cursor.execute("""
        SELECT s.first_name, s.last_name, s.age, s.gender,
               h.bmi, a.street, a.city, a.state, a.postal_code
        FROM students s
        LEFT JOIN health_stats h ON s.student_id = h.student_id
        LEFT JOIN address a ON s.student_id = a.student_id
        WHERE s.student_id = :1
    """, (sid,))
    row = cursor.fetchone()

    if row:
        student = {
            'student_id': sid,
            'first_name': row[0],
            'last_name': row[1],
            'age': row[2],
            'gender': row[3],
            'bmi': row[4],
            'street': row[5],
            'city': row[6],
            'state': row[7],
            'postal_code': row[8]
        }
        result=jsonify(student),200
    else:
        result = jsonify({"error": "Student not found"}), 404

    cursor.close()
    connection.close()

    return result


if __name__ == '__main__':
    app.run(debug=True)