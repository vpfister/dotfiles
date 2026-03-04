return {
  "greggh/claude-code.nvim",
  dependencies = {
    "nvim-lua/plenary.nvim",
  },
  config = function()
    local claude = require("claude-code")

    claude.setup({
      window = {
        split_ratio = 0.3,
        position = "botright",
        enter_insert = true,
      },
    })

    -- Switch layout and reopen the window if currently visible
    local function set_layout(position, ratio)
      claude.config.window.position = position
      claude.config.window.split_ratio = ratio
      local instance = claude.claude_code.current_instance
      local bufnr = instance and claude.claude_code.instances[instance]
      if bufnr then
        local wins = vim.fn.win_findbuf(bufnr)
        if #wins > 0 then
          claude.toggle() -- close
          claude.toggle() -- reopen with new settings
        end
      end
    end

    vim.api.nvim_create_user_command("ClaudeCodeRight", function()
      set_layout("botright vsplit", 0.5)
    end, { desc = "Claude Code: right panel 50%" })

    vim.api.nvim_create_user_command("ClaudeCodeBottom", function()
      set_layout("botright", 0.3)
    end, { desc = "Claude Code: bottom-right panel 30%" })

    local map_opts = { noremap = true, silent = true }
    vim.keymap.set("n", "<leader>cR", "<cmd>ClaudeCodeRight<CR>",
      vim.tbl_extend("force", map_opts, { desc = "Claude Code: right panel 50%" }))
    vim.keymap.set("n", "<leader>cB", "<cmd>ClaudeCodeBottom<CR>",
      vim.tbl_extend("force", map_opts, { desc = "Claude Code: bottom-right panel 30%" }))
  end,
}
