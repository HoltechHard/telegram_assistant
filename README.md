# Telegram Bot Assistant based on LLM + RAG and Escalation System  

### Components

- Kimi 2.5 LLM API  
- Python backend  
- Telegram bot: @holger_assistant_bot  
- Queue management  
- JSON database of subscribers and message interactions  
  
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
    
<img width="422" height="447" alt="image" src="https://github.com/user-attachments/assets/1d9a91e8-71bb-48c3-abbe-f2cec313546a" />  
   
### Multimodality Analysis  
      
<img width="1048" height="387" alt="image" src="https://github.com/user-attachments/assets/63d99159-c2fa-4e58-97bc-0b645f305db2" />   
   
   
    
   
