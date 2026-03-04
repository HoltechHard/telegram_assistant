# Telegram Bot Assistant based on LLM + RAG and Escalation System  

### Components

- Kimi 2.5 LLM API
- Python backend
- Telegram bot: @holger_assistant_bot
- Queue management
  
### Introduction  
  
A sophisticated Telegram bot system designed to manage channel communications with AI-powered question answering, automated broadcasts, and intelligent escalation to human support.  

  
### System Architecture  
  
<img width="1101" height="455" alt="image" src="https://github.com/user-attachments/assets/c599a47b-a08c-4606-8701-a88c92b49543" />

  
  
### Features  

🤖 AI-Powered Question Answering   
  
- Users can ask questions directly to the bot  
- Bot analyzes recent channel messages (last 24 hours) as context  
- Provides intelligent responses using LLM (Kimi/OpenAI compatible)  
- Queue-based processing for handling multiple concurrent users  
  
📢 Automated Broadcast System  
- When the owner posts in the channel, the bot schedules a broadcast  
- After a configurable delay (default: 1 hour), notifies all members  
- Excludes the owner from broadcast notifications  

⬆️ Intelligent Escalation  
- After each bot response, users see YES/NO satisfaction buttons    
- If user clicks YES: Consultation marked as complete  
- If user clicks NO: Query escalated to the channel owner  
- Owner receives full context including user info and question  
  
🔄 Queue-Based Processing  
- Handles multiple users simultaneously  
- Prevents API rate limit issues  
- Maintains response order  
    
  
### System Interaction  
    
<img width="412" height="442" alt="image" src="https://github.com/user-attachments/assets/32c6c3e4-f162-4ecf-ade8-4a40516e18b9" />

   
