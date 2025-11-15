#!/bin/bash

# Setup MCP servers for Claude Code
# This script adds commonly used MCP servers to Claude Code

echo "Adding MCP servers to Claude Code..."

# Add text-editor MCP server
echo "Adding text-editor..."
claude mcp add text-editor npx mcp-server-text-editor

# Add Context7 MCP server
echo "Adding context7..."
claude mcp add context7 npx -- -y @upstash/context7-mcp

# Add sequential-thinking MCP server
echo "Adding sequential-thinking..."
claude mcp add sequential-thinking npx -- -y @modelcontextprotocol/server-sequential-thinking

# Add playwright-stealth MCP server
echo "Adding playwright-stealth..."
claude mcp add playwright-stealth npx -- -y @pvinis/playwright-stealth-mcp-server

echo ""
echo "MCP servers added successfully!"
echo "Checking server health..."
echo ""

# List all configured MCP servers
claude mcp list

echo ""
echo "Setup complete! Restart Claude Code to use the new MCP servers."
echo "Command: exit and then claude"
