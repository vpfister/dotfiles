return {
  {
    "alexghergh/nvim-tmux-navigation",
    event = "VeryLazy",
    opts = {
      disable_when_zoomed = true,
    },
    keys = {
      { "<c-h>", "<cmd>NvimTmuxNavigateLeft<cr>", desc = "Navigate Left" },
      { "<c-j>", "<cmd>NvimTmuxNavigateDown<cr>", desc = "Navigate Down" },
      { "<c-k>", "<cmd>NvimTmuxNavigateUp<cr>", desc = "Navigate Up" },
      { "<c-l>", "<cmd>NvimTmuxNavigateRight<cr>", desc = "Navigate Right" },
    },
  },
}
