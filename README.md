# NSFW Media Detection Bot 🚨🤖

This Telegram bot scans **images, videos, stickers, GIFs, and animated stickers** sent in a group. If any media is NSFW, the bot will **delete it**, **send an alert**, and **log the incident** in a database.

## 🚀 Features  
1. **Automatic Media Scanning** – Detects NSFW content in images, videos, stickers, GIFs, and animated stickers.  
2. **Auto Deletion** – Deletes NSFW media immediately.  
3. **Alert System** – Notifies the group with a message mentioning the user and admins.  
4. **Logging & Database** – Tracks deleted media, users, and categories.  
5. **User Whitelist** – Admins can approve users whose media will never be deleted.  
6. **Personal Stats (`/myinfo`)** – Users can check how many times their media was deleted and in which categories.  
7. **Admin Commands** – Only the bot owner can add/remove users from the approved list.  

---

## 📂 Project Structure  

NSFW-Bot/ │── bot.py # Main bot logic (handles messages, detection, and deletion) │── predict.py # NSFW model loading and classification │── database.py # Handles user data, deleted media tracking, and whitelist │── config.py # Stores API keys, bot tokens, and settings │── utils.py # Helper functions (logging, file handling, user mentions) │── requirements.txt # Python dependencies │── README.md # Project documentation (this file) └── media/ # Temporary folder for downloading media files


---

## 🔧 Installation  

### **1️⃣ Install Dependencies**
Make sure you have Python installed, then run:  

```bash
pip install -r requirements.txt
2️⃣ Set Up Configuration
Edit config.py and add your Telegram bot token, admin IDs, and database credentials.

3️⃣ Run the Bot
Start the bot using:

bash
Copy
Edit
python bot.py
🔹 Commands
Command	Description
/myinfo	Shows user's NSFW deletion stats
/approve @user	Add a user to the approved list
/remove @user	Remove a user from the approved list
/start	Starts the bot
🔒 Admin Controls
Only the bot owner can approve or remove users from the whitelist.
The bot requires delete permissions in the group.
🤝 Contributions
Feel free to submit issues or pull requests!

📜 License
This project is open-source and free to use.

💡 Built with ❤️ using Python & TensorFlow. 🚀

---

### **🔹 What This `README.md` Includes:**
✅ **Project Overview**  
✅ **Features**  
✅ **Project Structure**  
✅ **Installation Steps**  
✅ **Commands List**  
✅ **Admin Controls**  
✅ **License & Contributions**  

Let me know if you need modifications! 🚀
