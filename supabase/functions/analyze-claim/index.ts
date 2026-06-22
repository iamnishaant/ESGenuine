import { serve } from "https://deno.land/std@0.168.0/http/server.ts";

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

serve(async (req) => {
  // Handle CORS preflight requests
  if (req.method === 'OPTIONS') {
    return new Response(null, { headers: corsHeaders });
  }

  try {
    const { claimText, companyName, sector } = await req.json();
    
    if (!claimText) {
      return new Response(
        JSON.stringify({ error: 'Claim text is required' }),
        { status: 400, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }

    const LOVABLE_API_KEY = Deno.env.get('LOVABLE_API_KEY');
    if (!LOVABLE_API_KEY) {
      console.error('LOVABLE_API_KEY is not configured');
      throw new Error('AI service not configured');
    }

    console.log('Analyzing claim for:', companyName, 'in sector:', sector);

    const systemPrompt = `You are an ESG (Environmental, Social, Governance) claim analysis expert for the PHAROS-INTEGRITY platform. Your job is to analyze corporate sustainability claims and identify:

1. **Claim Type**: Categorize the claim (e.g., Carbon Emissions, Renewable Energy, Water Conservation, Biodiversity, Supply Chain, Social Impact, Governance)
2. **Specificity Score** (1-10): How specific and measurable is the claim? Vague promises get low scores.
3. **Verifiability Score** (1-10): Can this claim be verified with satellite data, public records, or third-party audits?
4. **Key Metrics**: Extract any quantifiable targets or metrics mentioned
5. **Red Flags**: Identify potential greenwashing indicators or vague language
6. **Verification Approach**: Suggest data sources to verify (satellite imagery, regulatory filings, etc.)
7. **Risk Level**: Low, Medium, or High risk of being misleading

Be concise and actionable. Focus on what can be verified.`;

    const userPrompt = `Analyze this ESG claim from ${companyName || 'Unknown Company'} (${sector || 'Unknown Sector'}):

"${claimText}"

Provide your analysis in JSON format with these fields:
{
  "claimType": "string",
  "specificityScore": number,
  "verifiabilityScore": number,
  "keyMetrics": ["string"],
  "redFlags": ["string"],
  "verificationApproach": ["string"],
  "riskLevel": "Low" | "Medium" | "High",
  "summary": "string (2-3 sentences)"
}`;

    const response = await fetch('https://ai.gateway.lovable.dev/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${LOVABLE_API_KEY}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        model: 'google/gemini-3-flash-preview',
        messages: [
          { role: 'system', content: systemPrompt },
          { role: 'user', content: userPrompt }
        ],
      }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error('AI Gateway error:', response.status, errorText);
      
      if (response.status === 429) {
        return new Response(
          JSON.stringify({ error: 'Rate limit exceeded. Please try again later.' }),
          { status: 429, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
        );
      }
      if (response.status === 402) {
        return new Response(
          JSON.stringify({ error: 'AI credits depleted. Please add funds.' }),
          { status: 402, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
        );
      }
      
      throw new Error('Failed to analyze claim');
    }

    const data = await response.json();
    const content = data.choices?.[0]?.message?.content;
    
    console.log('AI response received:', content?.substring(0, 200));

    // Parse the JSON response from the AI
    let analysis;
    try {
      // Extract JSON from the response (handle markdown code blocks)
      const jsonMatch = content.match(/```json\n?([\s\S]*?)\n?```/) || content.match(/\{[\s\S]*\}/);
      const jsonStr = jsonMatch ? (jsonMatch[1] || jsonMatch[0]) : content;
      analysis = JSON.parse(jsonStr);
    } catch (parseError) {
      console.error('Failed to parse AI response as JSON:', parseError);
      // Return a structured response even if parsing fails
      analysis = {
        claimType: 'Unknown',
        specificityScore: 5,
        verifiabilityScore: 5,
        keyMetrics: [],
        redFlags: ['Unable to fully parse claim'],
        verificationApproach: ['Manual review recommended'],
        riskLevel: 'Medium',
        summary: content || 'Analysis could not be completed.'
      };
    }

    return new Response(
      JSON.stringify({ analysis }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );

  } catch (error) {
    console.error('Error in analyze-claim function:', error);
    return new Response(
      JSON.stringify({ error: error instanceof Error ? error.message : 'Unknown error' }),
      { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  }
});
