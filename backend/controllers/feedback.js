import feedbackReport from "../models/feedbackReport.js";
import { verifyToken } from "../utils/jwt.js";

const VALID_PAGES = new Set(["mixmatch", "glowup", "compatibility", "recommend", "other"]);

const normalizePage = (value) => {
  const page = String(value || "").trim().toLowerCase();
  if (!page) return "";
  if (VALID_PAGES.has(page)) return page;
  return "other";
};

export const submitFeedback = async (req, res) => {
  try {
    const page = normalizePage(req.body?.page);
    const message = String(req.body?.message || "").trim();

    if (!page) {
      return res.status(400).json({ message: "Feedback page is required." });
    }
    if (!message) {
      return res.status(400).json({ message: "Feedback message is required." });
    }
    if (message.length > 2000) {
      return res.status(400).json({ message: "Feedback message is too long." });
    }

    let userId = null;
    const authHeader = req.headers.authorization;
    if (authHeader) {
      const decoded = await verifyToken(authHeader);
      if (decoded?.id) {
        userId = decoded.id;
      }
    }

    const created = await feedbackReport.create({
      userId,
      page,
      message,
      status: "pending",
      details: {
        userAgent: String(req.headers["user-agent"] || ""),
      },
    });

    return res.status(201).json({
      message: "Feedback submitted.",
      reportId: String(created._id),
      status: created.status,
    });
  } catch (err) {
    console.error("submitFeedback error:", err);
    return res.status(500).json({ message: "Feedback submission failed." });
  }
};
