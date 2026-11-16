# chatstats

See how much you use each AI: chats, messages, rough token counts, busiest months and the
topics that keep coming up.

**Use it here: https://spencerrios64.github.io/chatstats/**

It is a single web page (`index.html`) with no dependencies and no server. Your files are
read in your browser and never uploaded. Works on desktop and on Android.

## Use

1. In each AI's settings, request a data export and download the file it sends you.
2. Open the page and pick all the export files at once.

You get: totals per AI, chats per month, the words that appear in the most chats, your
longest chats, and a table where you can type each AI's API price to see roughly what the
same chats would cost with API keys (useful for deciding when
[chatrelay](https://github.com/spencerrios64/chatrelay) should switch). **Download numbers**
saves the totals as a `.csv`.

## How to read the numbers

- Token counts are estimates: about 4 characters per token. Real counts differ by AI and
  language, often by 10 to 30 percent.
- Only text is counted. Images, files, web searches and hidden thinking are not in the
  exports, so real usage is higher.
- The cost table has no prices built in, because they change. Type them from each AI's
  pricing page. "Tokens sent" counts the whole chat so far for every reply.
- Gemini exports have no chats, only prompts per day, so each day counts as one chat.
- It reads export files. It cannot log in to your accounts or fetch chats by itself.
- **Claude** and **ChatGPT** exports are tested on small sample exports. **Gemini**, **Grok** and
  **DeepSeek** are read from their documented formats and have not been checked against real exports.
- Exports over 4 GB (zip64) aren't supported: unzip them and pick the `.json` inside.

Part of a family of small tools for AI chats: [chatvault](https://github.com/spencerrios64/chatvault), [chatzip](https://github.com/spencerrios64/chatzip), [chatrelay](https://github.com/spencerrios64/chatrelay), [chatbrief](https://github.com/spencerrios64/chatbrief), [chatscrub](https://github.com/spencerrios64/chatscrub), [chatcompare](https://github.com/spencerrios64/chatcompare), [chatstats](https://github.com/spencerrios64/chatstats) and [promptbank](https://github.com/spencerrios64/promptbank).
