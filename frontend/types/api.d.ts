/**
 * Hand-stubbed OpenAPI schema for the FigureMatch backend.
 *
 * Regenerate from the live spec with `pnpm gen:api` once the API is
 * deployed (P2.7+). For now this stub matches the endpoints that
 * exist as of P1.9: register, login, refresh, logout, me, health.
 *
 * Keep this file in sync with the backend until automated generation
 * kicks in.
 */

export interface paths {
  "/auth/register": {
    post: operations["register"];
  };
  "/auth/login": {
    post: operations["login"];
  };
  "/auth/refresh": {
    post: operations["refresh"];
  };
  "/auth/logout": {
    post: operations["logout"];
  };
  "/auth/me": {
    get: operations["me"];
  };
  "/content/generate": {
    post: operations["generateContent"];
  };
  "/content": {
    get: operations["listContent"];
  };
  "/content/{content_id}": {
    get: operations["getContent"];
    delete: operations["deleteContent"];
  };
  "/content/{content_id}/restore": {
    post: operations["restoreContent"];
  };
  "/content/{content_id}/image": {
    post: operations["generateImage"];
  };
  "/content/{content_id}/images": {
    get: operations["listImages"];
  };
  "/improve": {
    post: operations["improveText"];
  };
  "/improvements": {
    get: operations["listImprovements"];
  };
  "/improvements/{improvement_id}": {
    get: operations["getImprovement"];
    delete: operations["deleteImprovement"];
  };
  "/brand-voices": {
    get: operations["listBrandVoices"];
    post: operations["createBrandVoice"];
  };
  "/brand-voices/{voice_id}": {
    get: operations["getBrandVoice"];
    patch: operations["updateBrandVoice"];
    delete: operations["deleteBrandVoice"];
  };
  "/health": {
    get: operations["health"];
  };
  "/meta": {
    get: operations["meta"];
  };
}

export interface components {
  schemas: {
    User: {
      id: string;
      email: string;
      full_name: string;
      email_verified_at: string | null;
      last_login_at: string | null;
      created_at: string;
    };
    AuthResponse: {
      user: components["schemas"]["User"];
      access_token: string;
      token_type: "Bearer";
      expires_in: number;
    };
    RegisterRequest: {
      email: string;
      password: string;
      full_name: string;
    };
    LoginRequest: {
      email: string;
      password: string;
    };
    ErrorEnvelope: {
      error: {
        code: string;
        message: string;
        details: Record<string, unknown>;
      };
      meta: {
        request_id: string | null;
      };
    };

    // ── Content (Slice 2: all four text types) ───────────────────
    ContentType: "blog_post" | "linkedin_post" | "ad_copy" | "email";
    ResultParseStatus: "ok" | "retried" | "failed";
    BlogPostSection: {
      heading: string;
      body: string;
    };
    BlogPostResult: {
      title: string;
      meta_description: string;
      intro: string;
      sections: components["schemas"]["BlogPostSection"][];
      conclusion: string;
      suggested_tags: string[];
    };
    LinkedInPostResult: {
      hook: string;
      body: string;
      cta: string;
      hashtags: string[];
    };
    EmailResult: {
      subject: string;
      preview_text: string;
      greeting: string;
      body: string;
      cta_text: string;
      sign_off: string;
    };
    AdCopyFormat: "short" | "medium" | "long";
    AdCopyAngle:
      | "curiosity"
      | "social_proof"
      | "transformation"
      | "urgency"
      | "problem_solution";
    AdCopyVariant: {
      format: components["schemas"]["AdCopyFormat"];
      angle: components["schemas"]["AdCopyAngle"];
      headline: string;
      body: string;
      cta: string;
    };
    AdCopyResult: {
      variants: components["schemas"]["AdCopyVariant"][];
    };
    // Discriminated by `content_type` at the response level — but
    // openapi-typescript doesn't model discriminated unions natively,
    // so this is a flat union and the consumer narrows by inspecting
    // `content_type` on the response.
    ContentResult:
      | components["schemas"]["BlogPostResult"]
      | components["schemas"]["LinkedInPostResult"]
      | components["schemas"]["EmailResult"]
      | components["schemas"]["AdCopyResult"];
    GenerateRequest: {
      content_type: components["schemas"]["ContentType"];
      topic: string;
      tone?: string | null;
      target_audience?: string | null;
      brand_voice_id?: string | null;
    };
    GenerateUsage: {
      model_id: string;
      input_tokens: number;
      output_tokens: number;
      // Pydantic Decimal serializes as a string by default; the
      // frontend never does math on it, just displays it.
      cost_usd: string;
    };
    GenerateResponse: {
      content_id: string;
      content_type: components["schemas"]["ContentType"];
      result: components["schemas"]["ContentResult"] | null;
      rendered_text: string;
      result_parse_status: components["schemas"]["ResultParseStatus"];
      word_count: number;
      usage: components["schemas"]["GenerateUsage"];
      created_at: string;
    };

    // ── Dashboard list + detail (Slice 4) ────────────────────────
    ContentListItem: {
      id: string;
      content_type: components["schemas"]["ContentType"];
      topic: string;
      preview: string;
      word_count: number;
      model_id: string;
      result_parse_status: components["schemas"]["ResultParseStatus"];
      created_at: string;
    };
    PaginationMeta: {
      page: number;
      page_size: number;
      total: number;
      total_pages: number;
    };
    ListMeta: {
      request_id: string | null;
      pagination: components["schemas"]["PaginationMeta"];
    };
    ContentListResponse: {
      data: components["schemas"]["ContentListItem"][];
      meta: components["schemas"]["ListMeta"];
    };
    ContentDetailResponse: {
      id: string;
      content_type: components["schemas"]["ContentType"];
      topic: string;
      tone: string | null;
      target_audience: string | null;
      result: components["schemas"]["ContentResult"] | null;
      rendered_text: string;
      result_parse_status: components["schemas"]["ResultParseStatus"];
      word_count: number;
      model_id: string;
      created_at: string;
      deleted_at: string | null;
    };

    // ── Images (Slice 3) ─────────────────────────────────────────
    ImageStyle:
      | "photorealistic"
      | "illustration"
      | "minimalist"
      | "3d_render"
      | "watercolor"
      | "cinematic";
    ImageProvider: "openai" | "nova_canvas";
    GeneratedImage: {
      id: string;
      content_piece_id: string;
      style: string | null;
      provider: components["schemas"]["ImageProvider"];
      model_id: string;
      width: number;
      height: number;
      cdn_url: string;
      image_prompt: string;
      negative_prompt: string | null;
      cost_usd: string;
      is_current: boolean;
      created_at: string;
    };
    ImageGenerateRequest: {
      style?: components["schemas"]["ImageStyle"];
    };
    ImageGenerateResponse: {
      image: components["schemas"]["GeneratedImage"];
    };
    ImageListResponse: {
      data: components["schemas"]["GeneratedImage"][];
    };

    // ── Improver (Slice 5) ───────────────────────────────────────
    ImprovementGoal:
      | "shorter"
      | "persuasive"
      | "formal"
      | "seo"
      | "audience_rewrite";
    ImprovementChangesSummary: {
      tone_shift: string;
      length_change_pct: number;
      key_additions: string[];
      key_removals: string[];
    };
    ImproveRequest: {
      original_text: string;
      goal: components["schemas"]["ImprovementGoal"];
      new_audience?: string | null;
    };
    ImprovementResponse: {
      id: string;
      original_text: string;
      improved_text: string;
      goal: components["schemas"]["ImprovementGoal"];
      new_audience: string | null;
      explanation: string[];
      changes_summary: components["schemas"]["ImprovementChangesSummary"];
      original_word_count: number;
      improved_word_count: number;
      model_id: string;
      input_tokens: number;
      output_tokens: number;
      cost_usd: string;
      created_at: string;
      deleted_at: string | null;
    };
    ImprovementListItem: {
      id: string;
      goal: components["schemas"]["ImprovementGoal"];
      original_preview: string;
      improved_preview: string;
      original_word_count: number;
      improved_word_count: number;
      created_at: string;
    };
    ImprovementListResponse: {
      data: components["schemas"]["ImprovementListItem"][];
    };

    // ── Brand voices (Slice 6) ───────────────────────────────────
    BrandVoiceResponse: {
      id: string;
      name: string;
      description: string | null;
      tone_descriptors: string[];
      banned_words: string[];
      sample_text: string | null;
      target_audience: string | null;
      created_at: string;
      updated_at: string;
      deleted_at: string | null;
    };
    BrandVoiceListResponse: {
      data: components["schemas"]["BrandVoiceResponse"][];
    };
    BrandVoiceCreate: {
      name: string;
      description?: string | null;
      tone_descriptors?: string[];
      banned_words?: string[];
      sample_text?: string | null;
      target_audience?: string | null;
    };
    BrandVoiceUpdate: {
      name?: string;
      description?: string | null;
      tone_descriptors?: string[];
      banned_words?: string[];
      sample_text?: string | null;
      target_audience?: string | null;
    };

    // ── System ───────────────────────────────────────────────────
    MetaResponse: {
      provider_mode: "openai" | "mock" | "bedrock";
      app_version: string;
    };
  };
}

export interface operations {
  register: {
    requestBody: {
      content: {
        "application/json": components["schemas"]["RegisterRequest"];
      };
    };
    responses: {
      201: {
        content: {
          "application/json": components["schemas"]["AuthResponse"];
        };
      };
      409: {
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      422: {
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
    };
  };
  login: {
    requestBody: {
      content: {
        "application/json": components["schemas"]["LoginRequest"];
      };
    };
    responses: {
      200: {
        content: {
          "application/json": components["schemas"]["AuthResponse"];
        };
      };
      401: {
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
    };
  };
  refresh: {
    responses: {
      200: {
        content: {
          "application/json": components["schemas"]["AuthResponse"];
        };
      };
      401: {
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
    };
  };
  logout: {
    responses: {
      204: { content: never };
    };
  };
  me: {
    responses: {
      200: {
        content: {
          "application/json": components["schemas"]["User"];
        };
      };
      401: {
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
    };
  };
  health: {
    responses: {
      200: {
        content: {
          "application/json": {
            status: string;
            version: string;
            environment: string;
            dependencies: Record<string, string>;
          };
        };
      };
    };
  };
  meta: {
    responses: {
      200: {
        content: {
          "application/json": components["schemas"]["MetaResponse"];
        };
      };
    };
  };
  generateContent: {
    requestBody: {
      content: {
        "application/json": components["schemas"]["GenerateRequest"];
      };
    };
    responses: {
      200: {
        content: {
          "application/json": components["schemas"]["GenerateResponse"];
        };
      };
      401: {
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      422: {
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      429: {
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
    };
  };
  listContent: {
    parameters: {
      query?: {
        content_type?: components["schemas"]["ContentType"];
        q?: string;
        page?: number;
        page_size?: number;
      };
    };
    responses: {
      200: {
        content: {
          "application/json": components["schemas"]["ContentListResponse"];
        };
      };
      401: {
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
    };
  };
  getContent: {
    parameters: {
      path: { content_id: string };
    };
    responses: {
      200: {
        content: {
          "application/json": components["schemas"]["ContentDetailResponse"];
        };
      };
      401: {
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      404: {
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
    };
  };
  deleteContent: {
    parameters: {
      path: { content_id: string };
    };
    responses: {
      200: {
        content: {
          "application/json": components["schemas"]["ContentDetailResponse"];
        };
      };
      401: {
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      404: {
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
    };
  };
  restoreContent: {
    parameters: {
      path: { content_id: string };
    };
    responses: {
      200: {
        content: {
          "application/json": components["schemas"]["ContentDetailResponse"];
        };
      };
      401: {
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      404: {
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      422: {
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
    };
  };
  generateImage: {
    parameters: {
      path: { content_id: string };
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["ImageGenerateRequest"];
      };
    };
    responses: {
      200: {
        content: {
          "application/json": components["schemas"]["ImageGenerateResponse"];
        };
      };
      401: {
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      404: {
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      422: {
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
    };
  };
  listImages: {
    parameters: {
      path: { content_id: string };
    };
    responses: {
      200: {
        content: {
          "application/json": components["schemas"]["ImageListResponse"];
        };
      };
      401: {
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      404: {
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
    };
  };
  improveText: {
    requestBody: {
      content: {
        "application/json": components["schemas"]["ImproveRequest"];
      };
    };
    responses: {
      200: {
        content: {
          "application/json": components["schemas"]["ImprovementResponse"];
        };
      };
      401: {
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      422: {
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
    };
  };
  listImprovements: {
    responses: {
      200: {
        content: {
          "application/json": components["schemas"]["ImprovementListResponse"];
        };
      };
      401: {
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
    };
  };
  getImprovement: {
    parameters: {
      path: { improvement_id: string };
    };
    responses: {
      200: {
        content: {
          "application/json": components["schemas"]["ImprovementResponse"];
        };
      };
      401: {
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      404: {
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
    };
  };
  deleteImprovement: {
    parameters: {
      path: { improvement_id: string };
    };
    responses: {
      200: {
        content: {
          "application/json": components["schemas"]["ImprovementResponse"];
        };
      };
      401: {
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      404: {
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
    };
  };
  listBrandVoices: {
    responses: {
      200: {
        content: {
          "application/json": components["schemas"]["BrandVoiceListResponse"];
        };
      };
      401: {
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
    };
  };
  createBrandVoice: {
    requestBody: {
      content: {
        "application/json": components["schemas"]["BrandVoiceCreate"];
      };
    };
    responses: {
      201: {
        content: {
          "application/json": components["schemas"]["BrandVoiceResponse"];
        };
      };
      401: {
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      422: {
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
    };
  };
  getBrandVoice: {
    parameters: {
      path: { voice_id: string };
    };
    responses: {
      200: {
        content: {
          "application/json": components["schemas"]["BrandVoiceResponse"];
        };
      };
      401: {
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      404: {
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
    };
  };
  updateBrandVoice: {
    parameters: {
      path: { voice_id: string };
    };
    requestBody: {
      content: {
        "application/json": components["schemas"]["BrandVoiceUpdate"];
      };
    };
    responses: {
      200: {
        content: {
          "application/json": components["schemas"]["BrandVoiceResponse"];
        };
      };
      401: {
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      404: {
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      422: {
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
    };
  };
  deleteBrandVoice: {
    parameters: {
      path: { voice_id: string };
    };
    responses: {
      200: {
        content: {
          "application/json": components["schemas"]["BrandVoiceResponse"];
        };
      };
      401: {
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
      404: {
        content: {
          "application/json": components["schemas"]["ErrorEnvelope"];
        };
      };
    };
  };
}
